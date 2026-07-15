import os
import pickle

import gspread
import streamlit as st
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]


def autenticar():
    if 'gcp_service_account' in st.secrets:
        return gspread.service_account_from_dict(dict(st.secrets['gcp_service_account']))

    if 'token_pickle_b64' in st.secrets:
        import base64
        creds = pickle.loads(base64.b64decode(st.secrets['token_pickle_b64']))
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return gspread.authorize(creds)

    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if not os.path.exists('/mount/src'):
                with open('token.pickle', 'wb') as f:
                    pickle.dump(creds, f)
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            with open('token.pickle', 'wb') as f:
                pickle.dump(creds, f)

    return gspread.authorize(creds)
