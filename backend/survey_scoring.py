"""Versioned, deterministic questionnaire scoring; no AI calls."""
from copy import deepcopy

OPTIONS = ['Wcale nie dokuczały', 'Kilka dni', 'Więcej niż połowę dni', 'Niemal codziennie']
LABELS = [
    'Niewielkie zainteresowanie lub odczuwanie przyjemności z wykonywania czynności',
    'Uczucie smutku, przygnębienia lub beznadziejności',
    'Kłopoty z zaśnięciem lub przerywany sen, albo zbyt długi sen',
    'Uczucie zmęczenia lub brak energii',
    'Brak apetytu lub przejadanie się',
    'Poczucie niezadowolenia z siebie — lub uczucie, że jest się do niczego, albo że zawiódł/zawiodła Pan/Pani siebie lub rodzinę',
    'Problemy ze skupieniem się na przykład przy czytaniu gazety lub oglądaniu telewizji',
    'Poruszanie się lub mówienie tak wolno, że inni mogliby to zauważyć? Albo wręcz przeciwnie — niemożność usiedzenia w miejscu lub podenerwowanie powodujące ruchliwość znacznie większą niż zwykle',
    'Myśli, że lepiej byłoby umrzeć, albo chęć zrobienia sobie jakiejś krzywdy',
]
BANDS = [(4, 'Objawy minimalne'), (9, 'Łagodne nasilenie objawów'),
         (14, 'Umiarkowane nasilenie objawów'), (19, 'Umiarkowanie ciężkie nasilenie objawów'),
         (27, 'Ciężkie nasilenie objawów')]
DESCRIPTION = (
    'Jak często w ciągu ostatnich 2 tygodni dokuczały Panu/Pani następujące problemy? '
    'Proszę odpowiedzieć na wszystkie 9 pytań. Każda odpowiedź daje od 0 do 3 punktów. '
    'Po wysłaniu zobaczysz swój wynik. Autor ankiety widzi Twoje odpowiedzi i wynik. '
    'To badanie przesiewowe nasilenia objawów, a nie rozpoznanie depresji. '
    'Wynik należy omówić z lekarzem lub specjalistą zdrowia psychicznego.'
)


def phq9_preset():
    return deepcopy({'title': 'Przesiewowa ocena objawów depresji (PHQ-9)', 'description': DESCRIPTION,
        'scoring_profile': 'phq9', 'questions': [
            {'id': f'phq9_{index + 1}', 'label': label, 'type': 'select', 'required': True, 'options': OPTIONS}
            for index, label in enumerate(LABELS)], 'recipients': []})


def score(profile, answers):
    if profile != 'phq9' or answers is None:
        return None
    values = [OPTIONS.index(answers[f'phq9_{index}']) for index in range(1, 10)]
    total = sum(values)
    return {'profile': 'phq9', 'version': 1, 'total': total, 'maximum': 27,
            'items': [{'id': f'phq9_{index + 1}', 'label': LABELS[index],
                       'answer': answers[f'phq9_{index + 1}'], 'points': points}
                      for index, points in enumerate(values)],
            'severity': next(label for upper, label in BANDS if total <= upper),
            'follow_up_required': values[8] > 0,
            'note': 'Wynik przesiewowy opisuje nasilenie objawów i nie stanowi diagnozy. Omów go z lekarzem lub specjalistą zdrowia psychicznego.'}
