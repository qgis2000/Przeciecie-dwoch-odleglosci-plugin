# -*- coding: utf-8 -*-
# __init__.py  -  Plik wejściowy dla wtyczki
#     początek         : 2023-07-18
#     wersja           : 1.0.18
#.....data wersji......: 2024-12-29
#     autor            : Szymon Kędziora

def classFactory(iface):
    from .twoDistancesIntersectionPlugin import TwoDistancesIntersectionPlugin
    return TwoDistancesIntersectionPlugin(iface)


