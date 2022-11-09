import base64
import json
import os
import os.path
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel


class Present(BaseModel):
    name: str
    img_urls: list[str]
    description: str
    id: int


class MediaAttributes(BaseModel):
    media_path: str


class Media(BaseModel):
    attributes: MediaAttributes


class DescriptionAttributes(BaseModel):
    long_description: str
    language_id: int


class Description(BaseModel):
    attributes: DescriptionAttributes


class RawPresentPresentAttributes(BaseModel):
    nav_name: str
    media: list[Media]
    descriptions: list[Description]


class RawPresentPresent(BaseModel):
    attributes: RawPresentPresentAttributes


class RawPresent(BaseModel):
    present: RawPresentPresent
    present_id: int


load_dotenv()  # take environment variables from .env.

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def get_timestamp() -> int:
    d0 = date(1980, 1, 1)
    d1 = date.today()
    delta = d1 - d0
    return delta.days


def get_credentials():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def parse_present(present: RawPresent) -> Present:
    a = Present(
        name=present.present.attributes.nav_name,
        img_urls=[get_img_url(id.attributes.media_path) for id in present.present.attributes.media],
        description=next(dec.attributes.long_description for dec in present.present.attributes.descriptions if dec.attributes.language_id == 1),
        id=present.present_id
    )
    return a


def get_img_url(id: str):
    return f"https://system.gavefabrikken.dk/gavefabrikken_backend/views/media/user/{id}.jpg"


def get_token() -> str:
    url = "https://system.findgaven.dk/gavefabrikken_backend/index.php?rt=login/loginShopUser"
    payload = {
        "username": os.getenv("gusername"),
        "password": os.getenv("password"),
        'shop_id': '56',
        'logintype': 'shop'
    }
    response = requests.post(url, data=payload)
    return response.json()["data"]["result"][0]["token"]


def get_presents(token: str):
    url = "https://system.findgaven.dk/gavefabrikken_backend/index.php?rt=shop/readFull_v2"
    payload = {
        "token": token,
        "id": "56"
    }
    response = requests.post(url, data=payload)
    # print(response.json())
    return [parse_present(RawPresent(present=present["present"], present_id=present["present_id"])) for present in response.json()["data"]["shop"][0]["presents"]]


def create_message(sender: str, to: str, subject: str, message_data: dict[str, list[Present]]):
    message = MIMEMultipart("alternative")
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    # Create the plain-text and HTML version of your message
    text = "HTML not working"
    html = f"""
    <html>
        <body>
            <p>Her er en liste over nye gaver</p>
            <ul>
                {"".join([f"<li><a href='{present.img_urls[0]}'>{present.name}</a></li>" for present in message_data["new"]])}
            </ul>
            <p>Her er en liste over fjernede gaver</p>
            <ul>
                {"".join([f"<li><a href='{present.img_urls[0]}'>{present.name}</a></li>" for present in message_data["removed"]])}
            </ul>
        </body>
    </html>
    """

    # Turn these into plain/html MIMEText objects
    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")

    # Add HTML/plain-text parts to MIMEMultipart message
    # The email client will try to render the last part first
    message.attach(part1)
    message.attach(part2)
    return {'raw': base64.urlsafe_b64encode(message.as_string().encode()).decode()}


def send_new_presents(presents: dict[str, list[Present]]) -> None:
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    recipient = os.getenv("email")
    assert recipient is not None
    message = create_message(sender='me', to=recipient, subject='hello', message_data=presents)
    try:
        sent_message = (service.users().messages().send(userId="me", body=message).execute())
        print(f"Message Id: {sent_message['id']}")
    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f'An error occurred: {error}')


def save_presents(presents: list[Present]):
    with open(f"presents_{get_timestamp()}.json", "w") as f:
        f.write(json.dumps([present.dict() for present in presents]))


def save_ids(presents: list[Present]):
    with open("ids.json", "w") as f:
        f.write(json.dumps([present.id for present in presents]))


def get_old_present_data() -> list[Present]:
    try:
        with open(f"presents_{get_timestamp() - 1}.json", "r") as f:
            return [Present(**present) for present in json.loads(f.read())]
    except FileNotFoundError:
        return []


def get_new_presents(presents: list[Present]) -> dict[str, list[Present]]:
    removed_presents = []
    if os.path.exists("ids.json"):
        with open("ids.json", "r") as f:
            old_ids: list[int] = json.loads(f.read())
        new_ids = [present.id for present in presents]
        new_presents = [present for present in presents if present.id not in old_ids]
        removed_present_ids = [present for present in old_ids if present not in new_ids]
        if removed_present_ids:
            old_present_data = get_old_present_data()
            removed_presents = [present for present in old_present_data if present.id in removed_present_ids]
        return {
            "new": new_presents,
            "removed": removed_presents
        }
    else:
        return {
            "new": presents,
            "removed": []
        }


def main():
    token = get_token()
    presents = get_presents(token)
    save_presents(presents)
    new_presents = get_new_presents(presents)
    save_ids(presents)
    if new_presents:
        send_new_presents(new_presents)
    # print(presents)


if __name__ == "__main__":
    main()
