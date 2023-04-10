import json
import time

import httpx

# Define the range of IDs to fetch data for
id_range = range(1, 700)

# Initialize an empty dictionary to store the fetched data
places_dump = {}

# Iterate through the IDs and fetch data for each ID
for place_id in id_range:
    # Construct the URL for the API request
    url = (
        f'https://widget.profticket.ru/'
        f'api/company/data/?id={place_id}&language=ru-RU'
    )

    # Try to fetch the data from the API
    try:
        # Send the HTTP GET request to the API
        page = httpx.get(url)

        # Parse the JSON response
        file = json.loads(page.text)

        # Check if the response contains the required information
        if 'response' in file:
            # Extract the place name
            name = file['response']['name']

            # Add the place name to the dictionary
            places_dump[place_id] = name
            print(place_id, name)

            # Save the dictionary to a JSON file
            with open('profticket_test.json', 'w', encoding='utf-8') as f:
                json.dump(places_dump, f, ensure_ascii=False, indent=4)

    except Exception as e:
        # If an exception occurs, print the error message and wait for
        # 3 seconds before continuing
        print(e)
        time.sleep(3)
        continue
