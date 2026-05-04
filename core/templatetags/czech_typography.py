import re

from django import template


register = template.Library()

# Jednopísmenné české předložky/spojky, které nechceme nechat na konci řádku.
# Řeší i sousední dvojice typu: "a v březnu", "i v Praze", "s Janem".
_ONE_LETTER_WORDS_PATTERN = re.compile(
    r'(?m)(?:^|(?<=[\s(\["„‚»]))([AaIiKkOoSsUuVvZz])[\t ]+(?=\S)'
)

# Ručně zapsané nezlomitelné mezery v textu profilu.
# Podporujeme &nbsp;, &#160; i &#xA0;.
_MANUAL_NBSP_PATTERN = re.compile(
    r'&(?:nbsp|#160|#xA0);',
    re.IGNORECASE,
)


@register.filter
def cz_nbsp(value):
    """
    Doplní nezlomitelné mezery:
    - ručně tam, kde je v administraci zapsáno &nbsp;,
    - automaticky za jednopísmenné české předložky/spojky.

    Použití v šabloně:
        {{ person.bio|cz_nbsp|linebreaks }}

    Příklad v administraci:
        J.&nbsp;Křička
        H.&nbsp;Krása
    """
    if not value:
        return value

    text = str(value)

    # Ruční nezlomitelná mezera zapsaná staffem:
    # J.&nbsp;Křička -> J. Křička bez možnosti zalomení
    text = _MANUAL_NBSP_PATTERN.sub("\u00A0", text)

    # Automatické nezlomitelné mezery po jednopísmenných slovech
    text = _ONE_LETTER_WORDS_PATTERN.sub(
        lambda match: f"{match.group(1)}\u00A0",
        text,
    )

    return text