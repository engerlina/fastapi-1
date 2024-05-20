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
import markdown
import re

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

# Webflow API endpoint and headers
collection_id = "6645fd351283093f0f2eceac"  # Replace with your collection ID
api_token = os.environ.get("WEBFLOW_API_TOKEN")  # Get the API token from the environment variables
items_url = f"https://api.webflow.com/v2/collections/{collection_id}/items"
headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Bearer {api_token}"
}

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

        # Remove the trailing semicolon from the article_featured_image URL
        data.article_featured_image = data.article_featured_image.rstrip(';')

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

        print(f"Featured image resized and saved as {featured_image_filename}")

        # Resize the thumbnail image by 50%
        thumbnail_image = featured_image.copy()
        thumbnail_image.thumbnail((int(featured_image.width * 0.5), int(featured_image.height * 0.5)))

        # Save the thumbnail image
        thumbnail_image_filename = f"blogimages/{data.article_slug}-thumbnail.png"
        thumbnail_image_file = BytesIO()
        thumbnail_image.save(thumbnail_image_file, format="PNG")
        thumbnail_image_file.seek(0)

        print(f"Thumbnail image resized and saved as {thumbnail_image_filename}")

        # Upload the images to S3
        s3 = boto3.client("s3", aws_access_key_id=s3_access_key_id, aws_secret_access_key=s3_secret_access_key)
        
        print(f"Uploading featured image to S3 bucket: {s3_bucket_name}")
        s3.upload_fileobj(
            featured_image_file,
            s3_bucket_name,
            featured_image_filename,
            ExtraArgs={"ContentType": "image/png"}
        )
        featured_image_url = f"https://{s3_bucket_name}.s3.ap-southeast-2.amazonaws.com/{featured_image_filename}"
        print(f"Featured image uploaded successfully. URL: {featured_image_url}")
        
        print(f"Uploading thumbnail image to S3 bucket: {s3_bucket_name}")
        s3.upload_fileobj(
            thumbnail_image_file,
            s3_bucket_name,
            thumbnail_image_filename,
            ExtraArgs={"ContentType": "image/png"}
        )
        thumbnail_image_url = f"https://{s3_bucket_name}.s3.ap-southeast-2.amazonaws.com/{thumbnail_image_filename}"
        print(f"Thumbnail image uploaded successfully. URL: {thumbnail_image_url}")

        # Convert Markdown content to rich text format using markdown with tables extension
        article_content_richtext = markdown.markdown(data.article_content_markdown, extensions=['tables'])

        # Add custom CSS styles to the tables
        article_content_richtext = re.sub(
            r'<table>',
            '<table style="border-collapse: collapse; width: 100%; margin-bottom: 20px;">',
            article_content_richtext
        )
        article_content_richtext = re.sub(
            r'<th>',
            '<th style="border: 1px solid black; padding: 8px; text-align: left; background-color: #f2f2f2; font-weight: bold;">',
            article_content_richtext
        )
        article_content_richtext = re.sub(
            r'<td>',
            '<td style="border: 1px solid black; padding: 8px;">',
            article_content_richtext
        )

        # Update internal links to point to "/blog"
        article_content_richtext = re.sub(r'href="(?!https?://)', 'href="/blog/', article_content_richtext)

        # Prepare the payload for Webflow
        payload = {
            "fieldData": {
                "name": data.article_title,
                "slug": data.article_slug,
                "blog-post-excerpt": data.article_description,
                "blog-post-richt-text": article_content_richtext,
                "blog-post-featured-image-photo": {
                    "url": featured_image_url,
                    "alt": data.article_featured_image_alt_text
                },
                "blog-post-featured-image-illustration-3": {
                    "url": thumbnail_image_url,
                    "alt": data.article_featured_image_alt_text
                },
                "blog-post-category": "6645fd351283093f0f2ecf24",
                "blog-post-author": "6645fd351283093f0f2ece92"
            }
        }

        print(f"Webflow API URL: {items_url}")
        print(f"Webflow API Headers: {headers}")
        print(f"Webflow API Payload: {payload}")

        # Upload the data to Webflow
        response = requests.post(items_url, json=payload, headers=headers)
        print(f"Response from Webflow: {response.text}")

        if response.status_code == 200:
            return JSONResponse(content={"message": "Data uploaded to Webflow successfully"})
        else:
            error_message = f"Error uploading data to Webflow: {response.text}"
            print(error_message)
            raise Exception(error_message)

    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)
        raise HTTPException(status_code=500, detail=error_message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)