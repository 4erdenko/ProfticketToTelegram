import inspect

import pymorphy2

if not hasattr(inspect, 'getargspec'):
    def getargspec(func):
        spec = inspect.getfullargspec(func)
        return spec.args, spec.varargs, spec.varkw, spec.defaults
    inspect.getargspec = getargspec

morph = pymorphy2.MorphAnalyzer()


def pluralize(word, count):
    """
    Function to return the correct plural form of a word
    depending on the count.

    Args:
        word (str): The word to pluralize.
        count (int): The count to determine the correct plural form.

    Returns:
        str: The pluralized word.
    """
    parsed_word = morph.parse(word)[0]
    return parsed_word.make_agree_with_number(count).word
