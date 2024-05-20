import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
from typing import Optional
from pydantic import BaseModel
from PIL import Image
import requests
from io import BytesIO
import boto3

load_dotenv()

app = FastAPI()

class MachinedAIData(BaseModel):
    cluster_id: str
    cluster_topic: str
    cluster_audience: str
    article_id: str
    article_slug: str
    article_title: str
    article_description: str
    article_keyword: str
    article_content_markdown: str
    article_content_html: str
    article_featured_image: str
    article_featured_image_alt_text: str
    article_featured_image_caption: str
    article_setting_model: str
    article_setting_perspective: str
    article_setting_tone_of_voice: str

# AWS S3 credentials
s3_bucket_name = os.environ.get("S3_BUCKET_NAME")
s3_access_key_id = os.environ.get("S3_ACCESS_KEY_ID")
s3_secret_access_key = os.environ.get("S3_SECRET_ACCESS_KEY")

# Twitter API credentials
consumer_key = os.environ.get("TWITTER_CONSUMER_KEY")
consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET")
accounts = {}

def get_oauth_session(account_id):
    access_token = os.environ.get(f"{account_id}_ACCESS_TOKEN")
    access_token_secret = os.environ.get(f"{account_id}_ACCESS_TOKEN_SECRET")

    if not access_token or not access_token_secret:
        raise ValueError(f"Access token or access token secret not found for account '{account_id}'")

    return OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )

@app.on_event("startup")
async def startup_event():
    account_ids = ["JonochanScaleup", "SolopreneurLab", "Propunter", "LuckyLifeStories"]
    for account_id in account_ids:
        try:
            oauth = get_oauth_session(account_id)
            response = oauth.get("https://api.twitter.com/2/users/me")
            if response.status_code == 200:
                print(f"Authentication successful for account '{account_id}'")
            else:
                print(f"Authentication failed for account '{account_id}'. Please check the access token and access token secret.")
        except ValueError as e:
            print(str(e))

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        data = await request.json()
        account_id = data["account_id"]
        tweet_id = data.get("tweet_id")  # Use get() to handle None values
        tweet_text = data["tweet_text"]
        is_thread = data.get("is_thread", False)

        # Get OAuth1Session for the specified account
        oauth = get_oauth_session(account_id)

        if is_thread:
            if tweet_id is None:
                # If it's the first tweet in the thread and no tweet_id is provided,
                # post it as a new tweet without replying
                payload = {"text": tweet_text}
                response = oauth.post("https://api.twitter.com/2/tweets", json=payload)
                if response.status_code != 201:
                    raise Exception(f"Request returned an error: {response.status_code} {response.text}")
                tweet_data = response.json()
                tweet_id = tweet_data["data"]["id"]
            else:
                # Reply to the previous tweet in the thread
                payload = {"text": tweet_text, "reply": {"in_reply_to_tweet_id": tweet_id}}
                response = oauth.post("https://api.twitter.com/2/tweets", json=payload)
                if response.status_code != 201:
                    raise Exception(f"Request returned an error: {response.status_code} {response.text}")
                tweet_data = response.json()
                tweet_id = tweet_data["data"]["id"]
        else:
            # Post a single tweet
            payload = {"text": tweet_text}
            response = oauth.post("https://api.twitter.com/2/tweets", json=payload)
            if response.status_code != 201:
                raise Exception(f"Request returned an error: {response.status_code} {response.text}")

        return JSONResponse(content={"message": "Tweet posted successfully", "tweet_id": tweet_id})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/webhook/thread")
async def receive_thread_webhook(request: Request):
    try:
        data = await request.json()
        account_id = data["account_id"]
        thread_payload = data["thread_payload"]

        # Split the thread_payload into individual tweets
        tweets = thread_payload.split("\n")

        # Get OAuth1Session for the specified account
        oauth = get_oauth_session(account_id)

        tweet_id = None

        for tweet_text in tweets:
            # Skip empty or whitespace-only tweets
            if not tweet_text.strip():
                continue

            if tweet_id is None:
                # If it's the first tweet in the thread, post it as a new tweet
                payload = {"text": tweet_text.strip()}
                response = oauth.post("https://api.twitter.com/2/tweets", json=payload)
                if response.status_code != 201:
                    raise Exception(f"Request returned an error: {response.status_code} {response.text}")
                tweet_data = response.json()
                tweet_id = tweet_data["data"]["id"]
            else:
                # Reply to the previous tweet in the thread
                payload = {"text": tweet_text.strip(), "reply": {"in_reply_to_tweet_id": tweet_id}}
                response = oauth.post("https://api.twitter.com/2/tweets", json=payload)
                if response.status_code != 201:
                    raise Exception(f"Request returned an error: {response.status_code} {response.text}")
                tweet_data = response.json()
                tweet_id = tweet_data["data"]["id"]

        return JSONResponse(content={"message": "Thread posted successfully"})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/machinedai/")
async def receive_machinedai_data(data: MachinedAIData):
    try:
        # Print the received data in the console
        print("Received data from MachinedAI:")
        print(data)

        # Download the featured image
        response = requests.get(data.article_featured_image)
        image = Image.open(BytesIO(response.content))

        # Resize the featured image by 70%
        featured_image = image.copy()
        featured_image.thumbnail((int(image.width * 0.7), int(image.height * 0.7)))

        # Save the featured image
        featured_image_filename = f"blogimages/{data.article_slug}-featured.png"
        featured_image_file = BytesIO()
        featured_image.save(featured_image_file, format="PNG")
        featured_image_file.seek(0)

        # Resize the thumbnail image by 50%
        thumbnail_image = featured_image.copy()
        thumbnail_image.thumbnail((int(featured_image.width * 0.5), int(featured_image.height * 0.5)))

        # Save the thumbnail image
        thumbnail_image_filename = f"blogimages/{data.article_slug}-thumbnail.png"
        thumbnail_image_file = BytesIO()
        thumbnail_image.save(thumbnail_image_file, format="PNG")
        thumbnail_image_file.seek(0)

        # Upload the images to S3
        s3 = boto3.client("s3", aws_access_key_id=s3_access_key_id, aws_secret_access_key=s3_secret_access_key)
        s3.upload_fileobj(featured_image_file, s3_bucket_name, featured_image_filename)
        s3.upload_fileobj(thumbnail_image_file, s3_bucket_name, thumbnail_image_filename)

        return JSONResponse(content={"message": "Data received and images uploaded successfully"})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)