# import pymorphy2
#
# from services.profticket.profticket_api import ProfticketsInfo
# from settings import config
# from telegram.tg_utils import get_result_message
#
# # Initialize the pymorphy2 MorphAnalyzer for word declension
# morph = pymorphy2.MorphAnalyzer()
#
#
# def pluralize(word, count):
#     """
#     Function to return the correct plural form of a word
#     depending on the count.
#
#     Args:
#         word (str): The word to pluralize.
#         count (int): The count to determine the correct plural form.
#
#     Returns:
#         str: The pluralized word.
#     """
#     parsed_word = morph.parse(word)[0]
#     return parsed_word.make_agree_with_number(count).word
#
# def get_special_info(profticket: ProfticketsInfo, month=None,
#                      telegram_id=None):
#     """
#     Function to get all or personal performances in a specified month.
#
#     Args:
#         month (int, optional): Specifies an integer between 1 and 12.
#             If not specified, the default is the current month.
#         telegram_id (int, optional): If specified, a list of performances
#             that are assigned to the user in config.py will be returned.
#
#     Returns:
#         str: A list of performances for the specified month.
#     """
#
#     result = profticket.get_full_info()
#     if not result:
#         return 'Спектаклей в этом месяце нет.'
#     msg = ''
#     total = ''
#     show_count = 0
#     for item in result:
#         date = result[item]['date']
#         show_name = result[item]['show_name'].strip()
#         seats = int(result[item]['seats'])
#         if telegram_id is None:
#             show_count += 1
#             msg += get_result_message(seats, show_name, date)
#             total = f'Всего {show_count} {pluralize("спектакль", show_count)}🌚'
#         else:
#             if show_name in P_SHOWS.get(telegram_id):
#                 show_count += 1
#                 msg += get_result_message(seats, show_name, date)
#                 total = (
#                     f'Всего {show_count} {pluralize("спектакль", show_count)}🌚'
#                 )
#             elif msg == '':
#                 total = 'Нет спектаклей в этом месяце.'
#
#     return f'{msg}{total}'
#
