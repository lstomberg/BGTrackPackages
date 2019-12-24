#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Requires python 3.7+ for dataclass

# allows type hinting function return of class function is defined in
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, unique
import re

# ------------------
# Data storage class
# ------------------


@dataclass
class Address:
    line1: str
    line2: str
    city: str
    state: str
    zipcode: str
    recipient: str = None


@dataclass
class Email:
    Id: str
    to: str = field(compare=False)
    sender: str = field(compare=False)
    date: str = field(compare=False)
    subject: str = field(compare=False, default=None)


@unique
class BuyClub(Enum):
    MYS = "MYS"
    POINTSMAKER = "PointsMaker"
    USA = "USABuyingClub"
    BFMR = "BuyForMeRetail"

    @staticmethod
    def from_address(address: Address) -> BuyClub:
        line1 = address.line1.upper()
        # ^^^
        # MYS
        # ^^^
        if "144 QUIGLEY" in line1:
            return BuyClub.MYS
        # ^^^^^^^^^^^
        # POINTSMAKER
        # ^^^^^^^^^^^
        if "118 PARK" in line1:
            return BuyClub.POINTSMAKER
        if "200 BEDFORD FALLS" in line1:
            return BuyClub.POINTSMAKER
        # ^^^
        # USA
        # ^^^
        if "382 W RTE 59" in line1:
            return BuyClub.USA
        if "382 RTE 59" in line1:
            return BuyClub.USA
        if "382 ROUTE 59" in line1:
            return BuyClub.USA
        # ^^^^^^^^^^^^^^
        # BuyForMeRetail
        # ^^^^^^^^^^^^^^
        if "51" in line1 and "BROADWAY" in line1:
            return BuyClub.BFMR
        if "44 INDIAN ROCK" in line1:
            return BuyClub.BFMR
        if "24 TSIENNETO" in line1:
            return BuyClub.BFMR
        if "38 SPRING" in line1:
            return BuyClub.BFMR
        if "112" in line1 and "BROADWAY" in line1:
            return BuyClub.BFMR
        if "9 MAIN" in line1:
            return BuyClub.BFMR
        return None


@unique
class DeliveryService(Enum):
    UPS = "UPS"
    FedEx = "FedEx"
    USPS = "USPS"
    Amazon = "Amazon"

    @staticmethod
    def from_number(trk_number: str) -> DeliveryService:
        """
        Determine the service associated with a tracking number
        """
        if re.match("TBA", trk_number):
            return DeliveryService.Amazon
        if re.match("1Z", trk_number):
            return DeliveryService.UPS
        if re.fullmatch("[0-9]{20}", trk_number):
            return DeliveryService.USPS
        if re.fullmatch("[A-Z]{2}[0-9]{9}[A-Z]{2}", trk_number):
            return DeliveryService.USPS
        if re.fullmatch("[0-9]{12}", trk_number):
            return DeliveryService.FedEx
        if re.fullmatch("[0-9]{15}", trk_number):
            return DeliveryService.FedEx
        return None

#
# Main containing class
#


@dataclass
class Purchase:
    email: Email
    tracking_number: str
    address: Address = field(compare=False)
    # pylint: disable=used-before-assignment
    shipping_service: DeliveryService = field(init=False, compare=False)
    buying_club: BuyClub = field(init=False, compare=False)

    def __post_init__(self):
        self.shipping_service = DeliveryService.from_number(
            self.tracking_number)
        self.buying_club = BuyClub.from_address(self.address)
