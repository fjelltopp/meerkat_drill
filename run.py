import logging
from time import sleep, time

import redis
from meerkat_drill.message_service import send_batch_entries_to_sqs, notify_sns, SQS_QUEUE_NAME, DEAD_LETTER_QUEUE_NAME
from meerkat_drill import config

MAX_BATCH_SIZE = 10
BATCH_COLLECTION_TIMEOUT = 60
REDIS_QUEUE_NAME = 'nest-queue-' + config.country_config['country_name'].lower()
REDIS_IN_PROGRESS_QUEUE_NAME = 'nest-in-progress-queue-' + config.country_config['country_name'].lower()
redis_ = redis.StrictRedis(host='redis', port=6379, db=0)

def fetch_messages_from_queue(count=MAX_BATCH_SIZE):
    logging.info("Starting fetching messages from redis.")
    result = []
    start_time = time()
    elapsed_time = time() - start_time
    while elapsed_time < BATCH_COLLECTION_TIMEOUT or len(result) >= count:
        message = redis_.brpoplpush(REDIS_QUEUE_NAME, REDIS_IN_PROGRESS_QUEUE_NAME, 10)
        if message:
            result.append(message)
        elapsed_time = time() - start_time
    logging.info(f"Fetched {len(result)} records in {int(elapsed_time)} second.")
    return result

# 'Successful': [
#             {
#                 'Id': 'string',
#                 'MessageId': 'string',
#                 'MD5OfMessageBody': 'string',
#                 'MD5OfMessageAttributes': 'string',
#                 'SequenceNumber': 'string'
#             },
#         ],
#         'Failed': [
#             {
#                 'Id': 'string',
#                 'SenderFault': True|False,
#                 'Code': 'string',
#                 'Message': 'string'
#             },
#         ]

def main():
    messages = fetch_messages_from_queue(MAX_BATCH_SIZE)
    entries = []
    logging.info("Got message batch. Processing...")
    for i, message in enumerate(messages):
        entries.append(
            {
                "messageID": str(i),
                "messageBody": message
            }
        )
    sqs_response = send_batch_entries_to_sqs(entries)
    if sqs_response.get('Failed'):
        logging.error("Failed so send some messages to sqs")
    else:
        logging.info("Succesfully send batch to SQS.")
    logging.info("Removing send messages from redis")
    for success in sqs_response.get('Successful', []):
        message_id = int(success['MessageId'])
        message_sent = messages[message_id]
        redis_.lrem(REDIS_IN_PROGRESS_QUEUE_NAME, 0, message_sent)

    notify_sns()


if __name__ == '__main__':
    while True:
        main()
        sleep(1)


