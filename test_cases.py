import pytest
from unittest.mock import MagicMock, patch, mock_open
from sqs_message_receiver import (
    download_image,
    get_image_ext,
    process_message,
    send_to_dead_letter_queue,
    process_valid_message,
    save_original_image,
)


@pytest.fixture
def mock_sqs_client():
    return MagicMock()


@pytest.fixture
def mock_response_ok():
    response = MagicMock()
    response.status_code = 200
    response.content = b"sample_image_data"
    return response


@pytest.fixture
def mock_response_not_ok():
    response = MagicMock()
    response.status_code = 404
    return response


@pytest.fixture
def mock_originals_dir(tmpdir):
    return tmpdir.mkdir('originals')


@pytest.fixture
def mock_resized_dir(tmpdir):
    return tmpdir.mkdir('resized')


@pytest.fixture
def mock_message():
    return {
        'ReceiptHandle': 'dummy_receipt_handle',
        'Attributes': {'ApproximateReceiveCount': '1'},
        'Body': '{"id": "123", "image_url": "http://example.com/image.jpg"}'
    }


@pytest.fixture
def mock_image_data():
    mock_bytes_io = MagicMock()
    mock_bytes_io.getvalue.return_value = b"mock_image_data"
    return mock_bytes_io


def test_get_image_ext_with_jpg_extension():
    url = "http://example.com/image.jpg"
    ext = get_image_ext(url)
    assert ext == ".jpg"


def test_get_image_ext_with_png_extension():
    url = "http://example.com/image.png"
    ext = get_image_ext(url)
    assert ext == ".png"


def test_get_image_ext_without_extension():
    url = "http://example.com/image"
    ext = get_image_ext(url)
    assert ext == ".jpg"


def test_download_image_ok(mock_response_ok):
    url = "http://example.com/image.jpg"
    with patch('sqs_message_receiver.requests.get') as mock_get:
        mock_get.return_value = mock_response_ok
        image_data = download_image(url)
        assert image_data.getvalue() == b"sample_image_data"


def test_download_image_not_ok(mock_response_not_ok):
    url = "http://example.com/non_existent_image.jpg"
    with patch('sqs_message_receiver.requests.get') as mock_get,\
         patch('sqs_message_receiver.logger.error') as mock_logger_error:
        mock_get.return_value = mock_response_not_ok
        image_data = download_image(url)
        assert image_data is None
        mock_logger_error.assert_called_once_with(f"Failed to download image from URL: {url}")


def test_save_original_image(mock_image_data):
    original_image_path = "originals/original_image.jpg"
    with patch("builtins.open", mock_open()) as mock_file_handle:
        save_original_image(mock_image_data, original_image_path)
        mock_file_handle.assert_called_once_with(original_image_path, 'wb')
        mock_file_handle().write.assert_called_once_with(mock_image_data.getvalue())


def test_process_message_successful(mock_sqs_client, mock_message):
    with patch('sqs_message_receiver.process_valid_message') as mock_process_valid_message, \
            patch('sqs_message_receiver.send_to_dead_letter_queue') as mock_send_to_dead_letter_queue:
        process_message(mock_sqs_client, mock_message)
        assert mock_process_valid_message.called
        assert not mock_send_to_dead_letter_queue.called


def test_process_message_receive_count_exceeded(mock_sqs_client, mock_message):
    mock_message['Attributes']['ApproximateReceiveCount'] = '11'
    with patch('sqs_message_receiver.send_to_dead_letter_queue') as mock_send_to_dead_letter_queue:
        process_message(mock_sqs_client, mock_message)
        assert mock_send_to_dead_letter_queue.called
        assert mock_sqs_client.delete_message.called


def test_process_message_exception(mock_sqs_client, mock_message):
    with patch('sqs_message_receiver.process_valid_message') as mock_process_valid_message,\
         patch('sqs_message_receiver.logger.error') as mock_logger_error:
        mock_process_valid_message.side_effect = ValueError("Test error")
        process_message(mock_sqs_client, mock_message)
        mock_logger_error.assert_called_once_with("ValueError: Test error. Unable to parse message body as JSON.")


def test_process_valid_message_invalid_format(mock_message, mock_sqs_client):
    mock_message['Body'] = '{"invalid": "message"}'
    with patch('sqs_message_receiver.logger.error') as mock_logger_error:
        process_valid_message(mock_message, mock_sqs_client, 'sqs_queue_url', mock_message['ReceiptHandle'], mock_originals_dir,
                              mock_resized_dir)
        mock_logger_error.assert_called_once_with("Message format is invalid. Missing id or image_url.")
        assert not mock_sqs_client.delete_message.called


def test_process_valid_message_success(mock_message, mock_sqs_client, mock_originals_dir, mock_resized_dir):
    with patch('sqs_message_receiver.download_image') as mock_download_image, \
            patch('sqs_message_receiver.get_image_ext') as mock_get_image_ext, \
            patch('sqs_message_receiver.save_original_image') as mock_save_original_image, \
            patch('sqs_message_receiver.resize_and_save_image') as mock_resize_and_save_image, \
            patch('sqs_message_receiver.logger.info') as mock_logger_info:
        mock_download_image.return_value = MagicMock()
        mock_get_image_ext.return_value = '.jpg'

        process_valid_message(mock_message, mock_sqs_client, 'sqs_queue_url', mock_message['ReceiptHandle'],
                              mock_originals_dir,
                              mock_resized_dir)

        mock_download_image.assert_called_once_with('http://example.com/image.jpg')
        mock_get_image_ext.assert_called_once_with('http://example.com/image.jpg')
        mock_save_original_image.assert_called_once()
        mock_resize_and_save_image.assert_called_once()
        mock_logger_info.assert_called_once_with("Processed image 123 successfully.")
        mock_sqs_client.delete_message.assert_called_once_with(QueueUrl='sqs_queue_url',
                                                               ReceiptHandle=mock_message['ReceiptHandle'])


def test_send_to_dead_letter_queue(mock_sqs_client, mock_message):
    with patch('sqs_message_receiver.logger.error') as mock_logger_error:
        send_to_dead_letter_queue(mock_sqs_client, mock_message['Body'])
        mock_logger_error.assert_called_once_with("Message processing failed more than 10 times. Moving to dead letter queue.")
