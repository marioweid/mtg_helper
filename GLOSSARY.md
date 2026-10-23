# MTG Helper

Begriffe für Commander-bezogene Vorschläge und deren Prüfstand.

## Neue Karten

**Neue Karte**:
Eine erstmals innerhalb der letzten 60 UTC-Tage erschienene, Commander-legale Papierkarte,
die die bestehenden Quellenfilter und die Farbidentität der Commander-Konstellation erfüllt.
Spoiler und Neuauflagen alter Karten sind keine neuen Karten in diesem Sinn.
_Avoid_: Spoiler, Neuauflage

**Treffer**:
Eine für die betreffende Commander-Konstellation als stark passend oder testenswert bewertete
neue Karte, unabhängig von der tatsächlich gespielten Deckstrategie.
Diese KI-Einschätzung ist ungeprüfter Rat, keine bestätigte Regelauslegung.
_Avoid_: Geprüfte Empfehlung

**Commander-Konstellation**:
Der alleinige Commander oder die gemeinsam gespeicherten Commander eines Decks, einschließlich
eines zweiten Commanders oder Backgrounds. Sie bestimmt, für welche Commander
ein Vorschlag gilt, nicht welche Strategie das Deck tatsächlich verfolgt.
Die Konstellation ist keine Bestätigung einer regelkonformen Commander-Paarung.
_Avoid_: Deckstrategie, Deckinhalt

**Vollständige Prüfung**:
Eine Bewertung aller derzeit relevanten neuen Karten für eine Commander-Konstellation.
Auch abgelehnte Karten zählen als bewertet; ausstehende oder fehlgeschlagene Bewertungen nicht.
_Avoid_: Achterpaket, Teilergebnis

**Keine passenden Karten**:
Das Ergebnis einer vollständigen Prüfung ohne sichtbare Treffer bei ausreichend aktuellen Quellen.
Ein Fehler, ein veralteter Prüfstand oder eine noch unvollständige Prüfung ist kein solches Ergebnis.
_Avoid_: Noch keine Treffer, Prüfung fehlgeschlagen

**Prüfdelta**:
Die für eine Commander-Konstellation noch nicht oder nicht mehr aktuell bewerteten neuen Karten.
Ein erstmals verwendeter Commander hat auch dann ein Prüfdelta, wenn heute keine Karte erschienen ist.
_Avoid_: Tägliche Komplettprüfung

**Decklokales Ausblenden**:
Das Entfernen bereits enthaltener, als Addition geplanter oder in diesem Deck verworfener Karten
aus dessen Trefferanzeige. Die Commander-Bewertung und die Vorschläge anderer Decks bleiben gleich.
_Avoid_: Globale Ablehnung

**Tageslauf**:
Die automatische Bearbeitung des Prüfdelta aller verwendeten Commander-Konstellationen nach
dem erfolgreichen täglichen Katalogabgleich. Ein Tageslauf ist keine erneute Komplettbewertung.
_Avoid_: Deckanalyse, Tägliche Komplettprüfung

## Kartenlabels

**Oracle-Tag**:
Ein von Scryfall bereitgestelltes globales Kartenlabel mit eigener Identität und Zuordnungen zu
Oracle-Karten. Übergeordnete Tags können untergeordnete Tags einschließen, ohne die direkte
Zuordnung einer Karte zu verändern.
_Avoid_: Regeltag, MTGJSON-Tag, Hub-Tag

**Gedrucktes Keyword**:
Eine von Scryfall als Kartenfakt bereitgestellte benannte Fähigkeit oder Mechanik.
Es ist kein aus Regeltext oder einer fremden Keyword-Liste nachträglich abgeleitetes Label.
_Avoid_: Erkanntes MTGJSON-Keyword

**Persönliche Kategorie**:
Eine vom Nutzer für sein Deck gewählte Einordnung, unabhängig von globalen Oracle-Tags.
Sie ist Nutzerabsicht, keine Tatsachenbehauptung über die globale Kartenklassifikation.
_Avoid_: Globales Kartenlabel
