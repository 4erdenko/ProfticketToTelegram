from aiogram.types import ReplyKeyboardMarkup

# Keyboard for users with access to the personal shows section
keyboard_private = ReplyKeyboardMarkup(resize_keyboard=True)

# Keyboard for selecting the month in the personal shows section
keyboard_private_months = ReplyKeyboardMarkup(resize_keyboard=True)

# Main keyboard for users without access to the personal shows section
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

# Adding 'This Month' and 'Next Month' buttons to the main keyboard
keyboard.add('Этот месяц', 'Следующий месяц')

# Adding 'This Month', 'Next Month', and 'My Shows'
# buttons to the private keyboard
keyboard_private.add('Этот месяц', 'Следующий месяц').add('Мои спектакли')

# Adding 'This', 'Next', and '↩️' (back) buttons to the private months keyboard
keyboard_private_months.add('Этот', 'Следующий').add('↩️')
