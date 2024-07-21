# -*- coding: utf-8 -*-
# __init__.py  -  Plik wejściowy dla wtyczki
#     początek         : 2023-07-18
#     wersja           : 1.0.16
#.....data wersji......: 2024-04-01
#     autor            : Szymon Kędziora

def classFactory(iface):
    from .twoDistancesIntersectionPlugin import TwoDistancesIntersectionPlugin
    return TwoDistancesIntersectionPlugin(iface)


