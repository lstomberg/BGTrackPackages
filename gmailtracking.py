#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Requires python 3.7+ for dataclass

"""
This file uses google's APIs to load emails from Amazon and parse out tracking numbers.
It does so in multiple steps:
1. Find emails tagged with label current-organization-_bought-shipments
   (skip any already processed)
2. Download email as MimeMessage from email library
3. Use BeautifulSoup to parse HTML for URLs with 'ship' or 'track' in them, which
   is a heuristic for finding the URLs in an Amazon shipment notification email
4. Use requests to download the HTML from the located links
5. Parse the page with BeautifulSoup for an 'a' tag with the text beginning with "Tracking ID"
6. Strip the first 12 characters from the text (the length of "Tracking ID ")
7. Store email ID into text file so it isn't processed again
"""

# must be import first
from __future__ import print_function, annotations
# system imports next
import sys
from os import path
import base64
import email
import pickle
import requests
from urlextract import URLExtract
from cachetools import Cache
from typing import List, Dict
import re
# other APIs
from googleapiclient import discovery
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from bs4 import BeautifulSoup as Soup
import jsonpickle
from gmailtrackingmodel import Address, Email, Purchase, DeliveryService


# 7.3.6. Sections
# Section headers are created by underlining (and optionally overlining) the section title with a punctuation character, at least as long as the text:

# =================
# This is a heading
# =================
# Normally, there are no heading levels assigned to certain characters as the structure is determined from the succession of headings. However, for the Python documentation, here is a suggested convention:

# # with overline, for parts
# * with overline, for chapters
# =, for sections
# -, for subsections
# ^, for subsubsections
# ", for paragraphs

# ================
# Define constants
# ================


# for gmail APIs
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_PATH = path.join(path.dirname(path.realpath(__file__)), 'token.pickle')
CREDENTIALS_PATH = path.join(path.dirname(
    path.realpath(__file__)), 'credentials.json')

# store previously processed data
DATA_PATH = path.join(path.dirname(
    path.realpath(__file__)), 'tracking.data')
ERROR_PATH = path.join(path.dirname(
    path.realpath(__file__)), 'tracking.errors')


# ===============================
# Serialize previous runs to disk
# ===============================


# ----------------------
# Loading/saving to disk
# ----------------------

def save(itemlist: list, path: str):
    """
    Store a list of items to a file using json encoding
    """
    with open(path, "w+") as file:
        file.writelines([jsonpickle.encode(item) + "\n" for item in itemlist])


def append(item, path: str):
    """
    Appends a single item to a file using json encoding
    """
    with open(path, "a+") as file:
        file.write(jsonpickle.encode(item) + "\n")


def load(path: str) -> list:
    """
    Load a file that is encoded with each line containing a separate JSON object
    """
    try:
        with open(path) as file:
            return [jsonpickle.decode(line) for line in file]
    except:
        return []


# =============================
# encapsulate Gmail API calling
# =============================


class MemoryCache(Cache):
    """
    Necessary for using OAuth with gmail APIs
    """
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content


def get_gmail_service() -> discovery.Resource:
    """This function encapsulates gmail's OAuth token flow, requesting a new one if necessary

    Assumed
    -------
    TOKEN_PATH
    CREDENTIALS_PATH
    SCOPES

    Returns
    -------
    A gmail 'service' which can be used with gmail APIs
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

    service = discovery.build(
        'gmail', 'v1', credentials=creds, cache=MemoryCache(4))

    return service


# ------------------------
# Async loading from Gmail
# ------------------------


def get_messages(service: discovery.Resource, query: str, max_results: int = 400) -> List[Dict]:
    """Gets the email messages that match the query

    Args
    ----
      service: Authorized Gmail API service instance.
      query: A query string
      max_results: The maximum number of results to load

    Returns
    -------
      A list of message dictionaries
    """
    response = service.users().messages().list(
        userId="me", q=query, maxResults=max_results).execute()
    messages = response.get("messages")

    while 'nextPageToken' in response and len(messages) < max_results:
        page_token = response['nextPageToken']
        response = service.users().messages().list(
            userId="me", q=query, pageToken=page_token).execute()
        messages.extend(response['messages'])

    return messages


def GetMimeMessage(service: discovery.Resource, msg_id: str) -> email.message.Message:
    """Get a Message and use it to create a MIME Message.

    Args
    ----
      service: Authorized Gmail API service instance.
      msg_id: The ID of the Message required.

    Returns
    -------
      A MIME Message, consisting of data from Message.
    """
    message = service.users().messages().get(userId="me", id=msg_id,
                                             format='raw').execute()
    msg_str = base64.urlsafe_b64decode(
        message['raw'].encode('ASCII')).decode("utf-8")
    mime_msg = email.message_from_string(msg_str)
    return mime_msg


# ========================
# Logical steps for main()
# ========================

# -------------------------
# Initial loading functions
# -------------------------

def load_data() -> List[Purchase]:
    """
    Returns previously processed data
    """
    data = load(DATA_PATH)
    return data


def save_data(purchases: [Purchase]):
    """
    Saves purchases to data file
    """
    save(purchases, DATA_PATH)


def append_to_data(purchase: Purchase):
    """
    Appends email to data file
    """
    append(purchase, DATA_PATH)


def load_errors() -> List[Email]:
    """
    Returns previously processed errors
    """
    data = load(ERROR_PATH)
    return data


def append_to_errors(email: Email):
    """
    Appends email to data file
    """
    append(email, ERROR_PATH)


def get_message_count() -> int:
    """
    Checks commandline parameters for the number of messages to load, defaulting to 10
    """
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 75
    return count


# -----------------
# Parsing text/html
# -----------------

def parse_address(line1_2: str, city_state_zip: str) -> Address:
    # parse line1_2
    line1_2_matches = re.search(
        r'(.*) ((STE|UNIT|APT|DEPT|RM|FL|BLDG).*)', line1_2)
    line1 = line1_2_matches.group(1)
    line2 = line1_2_matches.group(2)
    # parse city/state/zip
    citystatezip_matches = re.search(
        r'([^,]*), ([A-Z]{2}).*?([0-9]{5})', city_state_zip)
    city = citystatezip_matches.group(1)
    state = citystatezip_matches.group(2)
    zipcode = citystatezip_matches.group(3)
    # return address
    address = Address(line1, line2, city, state, zipcode)
    return address


def find_amazon_tracking_urls_in_plaintext_body(text: str) -> str:
    """
    Locates Amazon URLs to tracking pages from plain text.  This is heuristically
    determined by finding urls containing both 'ship' and 'track'
    """
    urls = URLExtract().find_urls(text)
    amazon_url = next((x for x in urls if "ship" in x and "track" in x))
    return amazon_url


def find_amazon_tracking_ID_in_tracking_url_html(html: str) -> str:
    """
    Locates tracking number in html by searching all <a> tags that has inner text beginning
    with a predefined string.  Currently the string is "Tracking ID"
    """
    soup = Soup(html, "html.parser")
    atags = soup.findAll('a')
    text = next((x.text for x in atags if "Tracking ID" in x.text))
    # strip 'Tracking ID ' prefix
    tracking_number = text[13:]
    return tracking_number


# -------------
# network calls
# -------------

def get_email_body_as_plaintext(message: email.message.Message) -> str:
    """
    Loads a message and extracts the email body as plain text
    """
    # not necessairly the safest assumptions
    payload = message.get_payload(0).get_payload()
    return payload


def get_email_body_as_html(message: email.message.Message) -> str:
    """
    Loads a message and extracts the email body as HTML
    """
    # not necessairly the safest assumptions
    payload = message.get_payload(1).get_payload()
    return payload


def load_url(url: str) -> str:
    response = requests.get(url)
    return response.text


# ----------------------------
# Handle email based on sender
# ----------------------------

class DeliveryServiceParser:
    """
    This class defines the available means of delivery.

    Logic to parse emails for each of these is encapsulated in member functions.

    Functions:
      + parse_ds     -> DeliveryService
      + parse_address       -> Address
      + parse_tracking_id     -> String

    """

    UPS = "UPS"
    FedEx = "FedEx"
    USPS = "USPS"
    Amazon = "Amazon"

    @staticmethod
    def parse_ds(message: email.message.Message) -> DeliveryService:
        """
        Determine the service associated with the sender's email address
        """
        from_header = message["From"].lower()
        if "ups.com" in from_header:
            return DeliveryService.UPS
        if "fedex.com" in from_header:
            return DeliveryService.FedEx
        if "amazon.com" in from_header:
            return DeliveryService.Amazon
        return None

    @staticmethod
    def parse_address(ds: DeliveryService, message: email.message.Message) -> Address:
        """
        Switches on self and searches the email_body for the delivery address

        Returns
        -------
        Address parsed from email body text

        """
        # ^^^^^^^^^^^
        # switch: UPS
        # ^^^^^^^^^^^
        if ds == DeliveryService.UPS:
            plaintext_body = get_email_body_as_plaintext(message)
            # find address string
            match = re.search(
                r'Delivery Location:=C2=A0([^\n]*[\n][^\n]*)', plaintext_body)
            lines = match.group(1).splitlines()
            address = parse_address(lines[0], lines[1])
            return address

        # ^^^^^^^^^^^^^^
        # switch: Amazon
        # ^^^^^^^^^^^^^^
        if ds == DeliveryService.Amazon:
            html_body = get_email_body_as_html(message)
            soup = Soup(html_body, 'html.parser')
            address_tag = soup.find(id='3D"criticalInfo"').find("td")
            lines = [text for text in address_tag.stripped_strings]
            line1_2 = lines[1]
            city_state_zip = re.sub(r'[^\w ,]', '', lines[2])
            address = parse_address(line1_2, city_state_zip)
            address.recipient = re.sub(r'[^\w ]', '', lines[0])
            return address

        # ^^^^^^^^^^^^^^^
        # switch: default
        # ^^^^^^^^^^^^^^^
        return None

    @staticmethod
    def parse_tracking_id(ds: DeliveryService, message: email.message.Message) -> str:
        """
        Switches on self.  Determines tracking number in various ways.

        Returns
        -------
        Tracking number

        """
        # ^^^^^^^^^^^^^^
        # switch: Amazon
        # ^^^^^^^^^^^^^^
        if ds == DeliveryService.Amazon:
            plaintext_body = get_email_body_as_plaintext(message)
            # find amazon url
            tracking_url = find_amazon_tracking_urls_in_plaintext_body(
                plaintext_body)
            # load page
            html = load_url(tracking_url)
            # extract tracking id
            tracking_id = find_amazon_tracking_ID_in_tracking_url_html(html)
            # check for unhandled tracking number formats

            # THIS MEANS THE EMAIL WAS JUST AN AMAZON EMAIL, NOT ANY SORT OF SHIPMENT EMAIL
            # I NEED TO SPLIT UP 'RETAILER' FROM 'DELIVERYSERVICE' TO HANDLE AMAZON PROPERLY
            # if DeliveryService.from_number(tracking_id) != self:
            # print(
            #     f"Tracking number '{tracking_id}' does not match service {self}.  from_number API probably doesn't handle this format.")
            # return
            return tracking_id

        # ^^^^^^^^^^^^^^
        # switch: UPS
        # ^^^^^^^^^^^^^^
        if ds == DeliveryService.UPS:
            plaintext_body = get_email_body_as_plaintext(message)
            match = re.search(
                r'Tracking Number:=C2=A0([^\n\r]*)', plaintext_body)
            tracking_id = match.group(1)
            # check for unhandled tracking number formats
            # if DeliveryService.from_number(tracking_id) != self:
            # print(
            #     f"Tracking number '{tracking_id}' does not match service {self}.  from_number API probably doesn't handle this format.")
            return tracking_id

        # ^^^^^^^^^^^^^^^
        # switch: default
        # ^^^^^^^^^^^^^^^
        return None

# ----------------------
# primary execution code
# ----------------------


def main():
    # load purchases
    data = load_data()
    processed_ids = [x.email.Id for x in data]

    # load error emails
    errors = load_errors()

    # setup data
    newtrackingids = []
    load_count = get_message_count()

    query = "label: shipments"
    assert (len(query) != 0)

    service = get_gmail_service()

    # query gmail
    messages = get_messages(service, query, max_results=load_count)

    # filter ones where a purchase was found and loaded
    new_messages = [x for x in messages if x['id'] not in processed_ids]
    filtered_errors_handled = [x for x in new_messages if x not in errors]

    # process ids
    for message in filtered_errors_handled:
        message_id = message['id']

        # load email
        try:
            message = GetMimeMessage(service, message_id)
        except Exception as ex:
            print(
                f"Message (id: {message_id}) caused exception.  Skipping.\n{ex}")
            continue
        email = Email(
            message_id, message['To'], message['From'], message['Date'], message['Subject'])

        try:
            # determine email type - allows switching logic based on sender
            ds = DeliveryServiceParser.parse_ds(message)

            # get address
            address = DeliveryServiceParser.parse_address(ds, message)

            # get tracking number
            tracking_id = DeliveryServiceParser.parse_tracking_id(ds, message)

            # create @dataclass
            purchase = Purchase(email, tracking_id, address)

            if purchase not in data:
                # print
                print(purchase.buying_club)
                # store
                append_to_data(purchase)
                # store for easy printing at end
                newtrackingids.append(purchase.tracking_number)

        except Exception:
            # We dont actually handle all messages matching query, so some will throw an exception
            if email not in errors:
                append_to_errors(email)

    # print all new tracking numbers at end of script
    print('\n'.join(newtrackingids))
    # end function


# ===============
# Begin execution
# ===============
if __name__ == '__main__':
    main()
