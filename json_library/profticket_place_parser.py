import json
import time

import httpx

id_range = range(1, 700)
places_dump = {}

for place_id in id_range:
    url = (
        f'https://widget.profticket.ru/'
        f'api/company/data/?id={place_id}&language=ru-RU'
    )
    try:
        page = httpx.get(url)
        file = json.loads(page.text)
        if 'response' in file:
            name = file['response']['name']
            places_dump[place_id] = name
            print(place_id, name)

            with open('profticket_test.json', 'w', encoding='utf-8') as f:
                json.dump(places_dump, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(e)
        time.sleep(3)
        continue
