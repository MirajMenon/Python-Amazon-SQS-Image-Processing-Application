import os
import json
import boto3
import requests
from PIL import Image
from io import BytesIO
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS credentials and SQS queue name
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION_NAME = os.getenv('AWS_REGION_NAME', 'us-east-1')
SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL')
DEAD_LETTER_QUEUE_URL = os.getenv('DEAD_LETTER_QUEUE_URL')
ORIGINALS_DIR = "originals"
RESIZED_DIR = "resized"


def download_image(url):
    """Download image from URL."""
    response = requests.get(url)
    if response.status_code == 200:
        return BytesIO(response.content)
    else:
        logger.error(f"Failed to download image from URL: {url}")
        return None


def get_image_ext(url):
    """Extract image file extension."""
    _, ext = os.path.splitext(url)
    return ext if ext else '.jpg'


def save_original_image(image_data, original_image_path):
    """Save image data to file."""
    with open(original_image_path, 'wb') as f:
        f.write(image_data.getvalue())


def resize_and_save_image(image_data, resized_image_path):
    """Resize image and save."""
    image = Image.open(BytesIO(image_data.getvalue()))
    image.thumbnail((256, 256), Image.Resampling.LANCZOS)
    image.save(resized_image_path)


def receive_messages(sqs_client):
    """Receive messages from SQS queue."""
    while True:
        try:
            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                VisibilityTimeout=10,
                WaitTimeSeconds=20,
                AttributeNames=['All']
            )
            if 'Messages' in response:
                for message in response['Messages']:
                    process_message(sqs_client, message)
            else:
                logger.info("No messages received. Waiting for messages...")
        except Exception as e:
            logger.error(f"Error receiving messages from SQS: {e}")


def process_message(sqs_client, message):
    """Process message from SQS queue."""
    try:
        receipt_handle = message['ReceiptHandle']
        receive_count = int(message['Attributes']['ApproximateReceiveCount'])

        if receive_count > 10:
            send_to_dead_letter_queue(sqs_client=sqs_client,message=message['Body'])
            sqs_client.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
        else:
            process_valid_message(message, sqs_client, SQS_QUEUE_URL, receipt_handle, ORIGINALS_DIR, RESIZED_DIR)

    except ValueError as e:
        logger.error(f"ValueError: {e}. Unable to parse message body as JSON.")
    except Exception as e:
        logger.exception(f"Error processing message: {e}")


def process_valid_message(message, sqs_client, sqs_queue_url, receipt_handle, originals_dir, resized_dir):
    """Process valid message."""
    body = json.loads(message['Body'])
    image_id = body.get('id')
    image_url = body.get('image_url')

    if not image_id or not image_url:
        logger.error("Message format is invalid. Missing id or image_url.")
        return

    image_data = download_image(image_url)
    if image_data:
        image_ext = get_image_ext(image_url)

        original_image_path = os.path.join(originals_dir, f"{image_id}{image_ext}")
        save_original_image(image_data, original_image_path)

        resized_image_path = os.path.join(resized_dir, f"{image_id}{image_ext}")
        resize_and_save_image(image_data, resized_image_path)

        logger.info(f"Processed image {image_id} successfully.")
        sqs_client.delete_message(QueueUrl=sqs_queue_url, ReceiptHandle=receipt_handle)


def send_to_dead_letter_queue(sqs_client, message):
    """Sends the message to the dead letter queue."""
    logger.error("Message processing failed more than 10 times. Moving to dead letter queue.")
    sqs_client.send_message(
        QueueUrl=DEAD_LETTER_QUEUE_URL,
        MessageBody=message
    )


def main():
    try:
        required_env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'SQS_QUEUE_URL', 'DEAD_LETTER_QUEUE_URL']
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            exit(1)

        # Create directories if they don't exist
        os.makedirs(ORIGINALS_DIR, exist_ok=True)
        os.makedirs(RESIZED_DIR, exist_ok=True)

        # Initialize SQS client
        sqs_client = boto3.client('sqs', region_name=AWS_REGION_NAME,
                                  aws_access_key_id=AWS_ACCESS_KEY_ID,
                                  aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

        # Start receiving messages
        receive_messages(sqs_client)
    except KeyboardInterrupt:
        logger.info("Exiting...")


if __name__ == "__main__":
    main()
