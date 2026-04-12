1. Allways show Details
2. Add possibility to add collections (moxfield)
3. Create deck from moxfield link (ignore consider and sideboard)
4. When searching for a card, the deck stats are not updated f.e. added forrest still 0/36 lands
5. Basic Lands not shown in Land view
6. Add Basic Lands in Deck View
7. When searching for a card in land view f.e. a creeate it is still added in Lands



```text
The 30th Anniversary Edition (30A)
The 30th Anniversary Edition is explicitly non-tournament legal in all sanctioned formats. 

    Identification: These cards have a unique back that is different from the standard Magic back and are often treated as proxies in casual play.
    Filter Logic: Exclude cards with the set code 30A. 

2. Silver-Bordered and Acorn Sets
These sets are designed for casual "fun" play and break standard mechanical rules.

    Silver-Bordered Sets: Exclude sets like Unglued (UGL), Unhinged (UNH), and Unstable (UST).
    Acorn Cards: In the set Unfinity (UNF), only cards with an acorn-shaped holofoil stamp are illegal. Cards with a standard oval stamp in that same set are legal.
    Filter Logic: Filter by the border_color: silver attribute or specific security_stamp: acorn metadata. 

3. Gold-Bordered "Championship" Sets
These are official "printed proxies" of winning tournament decks and are illegal in all sanctioned play. 

    Sets to Exclude: World Championship Decks (WCxx), Collector’s Edition (CED), and International Edition (CEI).
    Filter Logic: Exclude by set codes or search for the border_color: gold attribute. 

4. Special Restricted Types 
Even in standard-bordered sets, specific card types are globally banned in Commander: 

    Conspiracies: Found in Conspiracy (CNS) and Conspiracy: Take the Crown (CN2), these are never legal in any deck.
    Ante Cards: Any card that refers to "playing for ante" (e.g., Contract from Below) is banned.
    Filter Logic: Exclude type: conspiracy and the specific list of roughly 9 ante-related cards. 
```