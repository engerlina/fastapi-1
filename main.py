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
    if account_id not in accounts:
        # Get request token
        request_token_url = "https://api.twitter.com/oauth/request_token?oauth_callback=oob&x_auth_access_type=write"
        oauth = OAuth1Session(consumer_key, client_secret=consumer_secret)
        fetch_response = oauth.fetch_request_token(request_token_url)
        resource_owner_key = fetch_response.get("oauth_token")
        resource_owner_secret = fetch_response.get("oauth_token_secret")
        print(f"Got OAuth token for account '{account_id}': {resource_owner_key}")

        # Get authorization
        base_authorization_url = "https://api.twitter.com/oauth/authorize"
        authorization_url = oauth.authorization_url(base_authorization_url)
        print(f"Please go here and authorize account '{account_id}': {authorization_url}")
        verifier = input(f"Paste the PIN for account '{account_id}' here: ")

        # Get the access token
        access_token_url = "https://api.twitter.com/oauth/access_token"
        oauth = OAuth1Session(
            consumer_key,
            client_secret=consumer_secret,
            resource_owner_key=resource_owner_key,
            resource_owner_secret=resource_owner_secret,
            verifier=verifier,
        )
        oauth_tokens = oauth.fetch_access_token(access_token_url)
        access_token = oauth_tokens["oauth_token"]
        access_token_secret = oauth_tokens["oauth_token_secret"]
        print(f"Access token for account {account_id}: {access_token}")
        print(f"Access token secret for account {account_id}: {access_token_secret}")

        accounts[account_id] = {
            "access_token": access_token,
            "access_token_secret": access_token_secret,
        }

    return OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=accounts[account_id]["access_token"],
        resource_owner_secret=accounts[account_id]["access_token_secret"],
    )

def check_authentication(account_id):
    if account_id not in accounts:
        print(f"Authentication required for account {account_id}.")
        get_oauth_session(account_id)
    else:
        oauth = OAuth1Session(
            consumer_key,
            client_secret=consumer_secret,
            resource_owner_key=accounts[account_id]["access_token"],
            resource_owner_secret=accounts[account_id]["access_token_secret"],
        )
        response = oauth.get("https://api.twitter.com/2/users/me")
        if response.status_code != 200:
            print(f"Authentication failed for account {account_id}. Please re-authorize.")
            del accounts[account_id]
            get_oauth_session(account_id)
        else:
            print(f"Authentication successful for account {account_id}.")

@app.on_event("startup")
async def startup_event():
    account_ids = ["JonochanScaleup", "SolopreneurLab", "Propunter", "LuckyLifeStories"]  # Replace with your account IDs
    for account_id in account_ids:
        check_authentication(account_id)

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        data = await request.json()
        account_id = data["account_id"]
        tweet_id = data["tweet_id"]
        tweet_text = data["tweet_text"]
        is_thread = data.get("is_thread", False)

        # Get OAuth1Session for the specified account
        oauth = get_oauth_session(account_id)

        if is_thread:
            # Create a tweet thread by replying to the first tweet
            if tweet_id is None:
                # If it's the first tweet in the thread, post it as a new tweet
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

        return JSONResponse(content={"message": "Tweet posted successfully"})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)