


def get_result_message(seats, show_name, date):
    """
    Function to create a message with information about a performance.

    Args:
        seats (int): Number of available seats.
        show_name (str): Name of the performance.
        date (str): Date of the performance.

    """
    if seats == 0:
        seats_text = '<code>SOLD OUT</code>'
    else:
        seats_text = f'Билетов: <code>{seats}</code>'

    return (
        f'📅<strong> {date}</strong>\n'
        f'💎 {show_name}\n'
        f'🎫 {seats_text}\n'
        '------------------------\n'
    )


def split_message_by_separator(
    message, separator='\n------------------------\n', max_length=MAX_MSG_LEN
):
    """

    Splits a message into chunks based on the provided separator.
    Ensures that each chunk is within the maximum length.

    Args:
        message (str):The message to split.
        separator (str, optional):The separator to split the message.
        max_length (int, optional):The maximum length of each chunk.
            Default is 4096.

    Returns:
        list: A list of message chunks.
    """
    chunks = []
    current_chunk = ''

    for block in message.split(separator):
        if len(current_chunk) + len(block) + len(separator) > max_length:
            chunks.append(current_chunk.rstrip())
            current_chunk = ''

        current_chunk += block + separator

    if current_chunk:
        chunks.append(current_chunk.rstrip())

    return chunks
