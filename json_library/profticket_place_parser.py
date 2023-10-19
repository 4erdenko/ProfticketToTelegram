import asyncio
import json
from tenacity import retry, stop_after_attempt, wait_fixed
import httpx


@retry(stop=stop_after_attempt(5), wait=wait_fixed(10))
async def fetch_place(client, place_id):
    url = f'https://widget.profticket.ru/api/company/data/?id={place_id}&language=ru-RU'
    page = await client.get(url)
    return page.json()


async def parser():
    # Define the range of IDs to fetch data for
    id_range = range(1, 700)

    # Initialize an empty dictionary to store the fetched data
    places_dump = {}
    async with httpx.AsyncClient() as client:
        # Iterate through the IDs and fetch data for each ID
        for place_id in id_range:
            try:
                file = await fetch_place(client, place_id)

                # Check if the response contains the required information
                if 'response' in file:
                    # Extract the place name
                    name = file['response']['name']

                    # Add the place name to the dictionary
                    places_dump[place_id] = name
                    print(place_id, name)

                    # Save the dictionary to a JSON file
                    with open(
                        'profticket_test.json', 'w', encoding='utf-8'
                    ) as f:
                        json.dump(places_dump, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f'Ошибка при обработке ID {place_id}: {e}')


if __name__ == '__main__':
    asyncio.run(parser())
