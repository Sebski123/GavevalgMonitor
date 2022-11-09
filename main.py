import os

import requests
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()  # take environment variables from .env.


class Present(BaseModel):
    name: str
    img_urls: list[str]
    description: str


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


def parse_present(present: RawPresent) -> Present:
    a = Present(
        name=present.present.attributes.nav_name,
        img_urls=[get_img_url(id.attributes.media_path) for id in present.present.attributes.media],
        description=next(dec.attributes.long_description for dec in present.present.attributes.descriptions if dec.attributes.language_id == 1)
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
    return [parse_present(RawPresent(present=present["present"])).dict() for present in response.json()["data"]["shop"][0]["presents"]]


#
def main():
    token = get_token()
    presents = get_presents(token)
    print(presents)


if __name__ == "__main__":
    main()
