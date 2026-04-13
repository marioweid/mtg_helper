1. Remove Chat from deck view
2. List that shows card in category so that if adding a card you can also remove it again if you dont want it anymore
3. The agent that creates the deck description also changes the amount of card draw/ramp etc. based on the chat with the user and his preffers
4. Land view shows Sol RIng and not only lands
5. energy as a metadata filter
6. Warping Wail, Kozilek's Command, Eldrazi Confluence often shown in bangers etc. even though they dont even fit (looks a bit like eldrazi get high priority)

```text
The 30th Anniversary Edition (30A)
The 30th Anniversary Edition is explicitly non-tournament legal in all sanctioned formats. 

    Identification: These cards have a unique back that is different from the standard Magic back and are often treated as proxies in casual play.
    Filter Logic: Exclude cards with the set code 30A. 

1. Silver-Bordered and Acorn Sets
These sets are designed for casual "fun" play and break standard mechanical rules.

    Silver-Bordered Sets: Exclude sets like Unglued (UGL), Unhinged (UNH), and Unstable (UST).
    Acorn Cards: In the set Unfinity (UNF), only cards with an acorn-shaped holofoil stamp are illegal. Cards with a standard oval stamp in that same set are legal.
    Filter Logic: Filter by the border_color: silver attribute or specific security_stamp: acorn metadata. 

1. Gold-Bordered "Championship" Sets
These are official "printed proxies" of winning tournament decks and are illegal in all sanctioned play. 

    Sets to Exclude: World Championship Decks (WCxx), Collector’s Edition (CED), and International Edition (CEI).
    Filter Logic: Exclude by set codes or search for the border_color: gold attribute. 

1. Special Restricted Types 
Even in standard-bordered sets, specific card types are globally banned in Commander: 

    Conspiracies: Found in Conspiracy (CNS) and Conspiracy: Take the Crown (CN2), these are never legal in any deck.
    Ante Cards: Any card that refers to "playing for ante" (e.g., Contract from Below) is banned.
    Filter Logic: Exclude type: conspiracy and the specific list of roughly 9 ante-related cards. 
```

# Moxfield
2. Add possibility to add collections (moxfield)
3. Create deck from moxfield link (ignore consider and sideboard)