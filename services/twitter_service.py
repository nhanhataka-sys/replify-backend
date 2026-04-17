import logging
import tweepy

logger = logging.getLogger(__name__)


def _make_client(
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
) -> tweepy.Client:
    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )


def post_thread(
    tweets: list[str],
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
) -> list[str]:
    """Post a list of tweets as a reply thread. Returns the list of posted tweet IDs."""
    client = _make_client(api_key, api_secret, access_token, access_token_secret)

    tweet_ids: list[str] = []
    reply_to_id: str | None = None

    for i, text in enumerate(tweets):
        kwargs: dict = {"text": text}
        if reply_to_id:
            kwargs["in_reply_to_tweet_id"] = reply_to_id

        response = client.create_tweet(**kwargs)
        tweet_id = str(response.data["id"])
        tweet_ids.append(tweet_id)
        reply_to_id = tweet_id
        logger.info("Posted tweet %d/%d — id=%s", i + 1, len(tweets), tweet_id)

    return tweet_ids
