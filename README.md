# BGTrackPackages
Pulls tracking numbers from gmail and stores information on buying group destination and email

## Installation

1. Install python 3.7+ or newer.  
2. Then install the requirements for this script.

```sh
pip install -r require.txt
```

3. Follow the first two steps on the Gmail [quickstart guide](https://developers.google.com/gmail/api/quickstart/python) to create a credentials.json file that allows you to access your gmail account via web services.
4. Set up the `query` value in gmailtracking.py to find all shipment tracking emails.  I recommend configuring a label rule in gmail and querying for all emails with that label to keep this script simple.
