from aiogram.types import ReplyKeyboardMarkup

keyboard_private = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard_private_months = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add('Этот месяц', 'Следующий месяц')
keyboard_private.add('Этот месяц', 'Следующий месяц').add('Мои спектакли')
keyboard_private_months.add('Этот', 'Следующий').add('↩️')
