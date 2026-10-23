# Keep legacy English imports working through the shared presenter.
from .i18n.presentation import TECHNICAL_FIELDS, present, presenter
from .i18n.presentation import translate_text as _translate_text


def reference():
    return presenter('en').reference


def translate_text(value):
    return _translate_text(value, 'en')


def english_presentation(value, field=''):
    return present(value, 'en', field)
