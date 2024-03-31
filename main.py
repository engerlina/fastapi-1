import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

load_dotenv()

app = FastAPI()

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)