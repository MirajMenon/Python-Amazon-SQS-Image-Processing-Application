# Python-Amazon-SQS-Image-Processing-Application

This Python application is designed to receive messages from an Amazon SQS queue.
Each message contains a JSON payload specifying an ID and its image URL. 
The application downloads the image from the provided URL, saves the original image, resizes it to ensure the largest edge is 256px, and saves the resized image. 
Additionally, if message processing fails more than 10 times, the message is moved to a dead letter queue.

### JSON Payload Format

A Message in the SQS queue should have the following JSON payload format:

```
{
    "id": "123",
    "image_url": "https://example.com/image.jpg"
}
```

### Install dependencies:
Use Python 3.8 or newer.

``` pip install -r requirements.txt ```

### Configuration
Before running the application, ensure that the following environment variables are set:

```
AWS_ACCESS_KEY_ID: AWS access key ID.
AWS_SECRET_ACCESS_KEY: AWS secret access key.
AWS_REGION_NAME: AWS region name (default is us-east-1).
SQS_QUEUE_URL: URL of the Amazon SQS queue.
DEAD_LETTER_QUEUE_URL: URL of the dead letter queue.
```

### Usage

Run the application using Python.

``` 
python sqs_message_receiver.py 
```

### Testing

Unit tests are implemented using pytest. To run tests, execute:

``` 
pytest 
```

### Workflow
For each message received from the SQS queue, the application performs the following steps:

1. Parses the message body to extract the ID and image URL.
2. Downloads the image from the specified URL.
3. Stores the original image in the "originals" directory with the file named using the ID and appropriate file extension.
4. Resizes the image so the largest edge is 256px.
5. Stores the resized image in the "resized" directory.
6. If message processing fails and the message has been received from the queue more than 10 times, the message is placed on a dead letter queue.



