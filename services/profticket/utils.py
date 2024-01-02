# from services.profticket.profticket_api import ProfticketsInfo
# from settings import config
# from telegram.tg_utils import get_result_message
#
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
