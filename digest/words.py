"""Built-in word-of-the-day list, used when no LLM is configured.

Words are chosen deterministically from the date, so the list cycles without
repeats for len(WORDS) days.
"""
from __future__ import annotations

import re
from datetime import date

from .models import Story, WordOfTheDay

# (word, pronunciation, part of speech, definition, example, origin)
WORDS = [
    ("sanguine", "SANG-gwin", "adjective", "Optimistic or positive, especially in a difficult situation.",
     "Markets remained sanguine despite the central bank's warning.", "Latin sanguis, 'blood' — once thought to govern cheerfulness."),
    ("hegemony", "hi-JEM-uh-nee", "noun", "Leadership or dominance, especially by one state over others.",
     "Analysts debated whether the era of American hegemony was ending.", "Greek hēgemonia, 'leadership'."),
    ("obfuscate", "OB-fuh-skayt", "verb", "To make something unclear or harder to understand, often deliberately.",
     "The report seemed designed to obfuscate the true cost of the project.", "Latin obfuscare, 'to darken'."),
    ("perspicacious", "pur-spi-KAY-shus", "adjective", "Having a ready insight into things; shrewd.",
     "A perspicacious columnist saw the housing slowdown coming a year early.", "Latin perspicax, 'sharp-sighted'."),
    ("détente", "day-TAHNT", "noun", "The easing of hostility or strained relations between countries.",
     "The summit raised hopes of a détente between the two rivals.", "French, 'loosening, relaxation'."),
    ("ephemeral", "ih-FEM-er-ul", "adjective", "Lasting for a very short time.",
     "Many viral apps prove ephemeral, fading within a season.", "Greek ephēmeros, 'lasting a day'."),
    ("intransigent", "in-TRAN-suh-junt", "adjective", "Unwilling to change one's views or to agree about something.",
     "Negotiations stalled as both sides remained intransigent.", "Spanish los intransigentes, a 19th-century political faction."),
    ("gentrification", "jen-truh-fi-KAY-shun", "noun", "The process by which a poorer area is changed by wealthier people moving in, often displacing existing residents.",
     "Rising rents signalled the neighbourhood's rapid gentrification.", "Coined by sociologist Ruth Glass in 1964, from 'gentry'."),
    ("sclerotic", "skluh-ROT-ik", "adjective", "Losing the ability to adapt; rigid and unresponsive.",
     "Critics called the permitting system sclerotic.", "Greek sklēros, 'hard'."),
    ("panacea", "pan-uh-SEE-uh", "noun", "A solution or remedy for all difficulties.",
     "AI is not a panacea for slow economic growth.", "Greek panakeia, from Panakeia, goddess of healing."),
    ("realpolitik", "ray-AHL-poh-li-teek", "noun", "Politics based on practical objectives rather than ideals.",
     "The deal was a piece of cold realpolitik.", "German, 'politics of reality'."),
    ("verisimilitude", "ver-uh-si-MIL-i-tood", "noun", "The appearance of being true or real.",
     "Deepfakes achieve an unsettling verisimilitude.", "Latin verisimilis, 'probable'."),
    ("bellwether", "BEL-weth-er", "noun", "Something that leads or indicates trends.",
     "The city's condo market is a bellwether for the region.", "The belled wether (castrated ram) that led a flock."),
    ("insouciant", "in-SOO-see-unt", "adjective", "Showing a casual lack of concern; indifferent.",
     "Investors seemed insouciant about rising rates.", "French, from in- 'not' + soucier 'to care'."),
    ("pernicious", "per-NISH-us", "adjective", "Having a harmful effect, especially gradually or subtly.",
     "Misinformation has a pernicious effect on public trust.", "Latin perniciosus, 'destructive'."),
    ("quixotic", "kwik-SOT-ik", "adjective", "Exceedingly idealistic; unrealistic and impractical.",
     "His quixotic campaign for a global tax drew polite applause.", "From Don Quixote, Cervantes' idealistic hero."),
    ("amortize", "AM-er-tize", "verb", "To gradually pay off a debt through regular payments.",
     "A 30-year mortgage amortizes slowly in the early years.", "Old French amortir, 'to deaden, extinguish'."),
    ("brinkmanship", "BRINK-mun-ship", "noun", "Pushing a dangerous situation to the edge of disaster to gain an advantage.",
     "The debt-ceiling standoff was a familiar exercise in brinkmanship.", "Popularised in 1956 to describe Cold War diplomacy."),
    ("salient", "SAY-lee-unt", "adjective", "Most noticeable or important.",
     "The salient point is that supply has not kept up with demand.", "Latin salire, 'to leap'."),
    ("hubris", "HYOO-bris", "noun", "Excessive pride or self-confidence.",
     "The startup's collapse was a lesson in hubris.", "Greek hybris, 'insolence, outrage'."),
    ("equivocate", "ih-KWIV-uh-kayt", "verb", "To use ambiguous language to conceal the truth or avoid committing oneself.",
     "The minister equivocated when asked about the sanctions.", "Latin aequivocus, 'of identical sound'."),
    ("zeitgeist", "TSITE-gyste", "noun", "The defining spirit or mood of a particular period.",
     "Her column captured the anxious zeitgeist of the AI boom.", "German Zeit 'time' + Geist 'spirit'."),
    ("recalcitrant", "ri-KAL-si-trunt", "adjective", "Having an uncooperative attitude toward authority.",
     "Recalcitrant members blocked the reform bill.", "Latin recalcitrare, 'to kick back'."),
    ("serendipity", "ser-un-DIP-i-tee", "noun", "The occurrence of happy discoveries by chance.",
     "Penicillin's discovery is a classic tale of serendipity.", "Coined by Horace Walpole from the tale 'The Three Princes of Serendip'."),
    ("cognoscenti", "kon-yuh-SHEN-tee", "noun", "People considered especially well informed about a subject.",
     "The cognoscenti predicted the rate cut weeks ago.", "Italian, 'those who know'."),
    ("exacerbate", "ig-ZAS-er-bayt", "verb", "To make a problem or bad situation worse.",
     "Restrictive zoning exacerbates the housing shortage.", "Latin exacerbare, 'to irritate'."),
    ("bifurcate", "BY-fer-kayt", "verb", "To divide into two branches or parts.",
     "The global economy may bifurcate into rival tech blocs.", "Latin bifurcus, 'two-forked'."),
    ("sinecure", "SY-ni-kyoor", "noun", "A position requiring little work but giving status or pay.",
     "The ambassadorship was no sinecure in wartime.", "Latin sine cura, 'without care'."),
    ("probity", "PROH-bi-tee", "noun", "The quality of having strong moral principles; honesty.",
     "Voters want probity from those handling public funds.", "Latin probitas, 'goodness'."),
    ("liminal", "LIM-uh-nul", "adjective", "Occupying a position at, or on both sides of, a boundary or threshold.",
     "Remote work left office districts in a liminal state.", "Latin limen, 'threshold'."),
    ("fecund", "FEK-und", "adjective", "Producing or capable of producing an abundance of new growth or ideas.",
     "Bell Labs was a fecund environment for invention.", "Latin fecundus, 'fruitful'."),
    ("acrimonious", "ak-ruh-MOH-nee-us", "adjective", "Angry and bitter, typically of speech or debate.",
     "The trade talks ended in acrimonious fashion.", "Latin acrimonia, 'sharpness'."),
    ("parsimonious", "par-suh-MOH-nee-us", "adjective", "Unwilling to spend money or use resources; frugal to excess.",
     "A parsimonious budget left little for research.", "Latin parsimonia, 'frugality'."),
    ("solipsistic", "sol-ip-SIS-tik", "adjective", "Very self-centred; treating oneself as the only thing that matters.",
     "Critics called the tech mogul's worldview solipsistic.", "Latin solus 'alone' + ipse 'self'."),
    ("juggernaut", "JUG-er-nawt", "noun", "A huge, powerful, and overwhelming force.",
     "The chipmaker has become a market juggernaut.", "Hindi Jagannāth, a form of Vishnu whose chariot was paraded."),
    ("anodyne", "AN-uh-dyne", "adjective", "Not likely to provoke dissent or offence; deliberately bland.",
     "The communiqué was anodyne, revealing little.", "Greek anōdynos, 'painless'."),
    ("halcyon", "HAL-see-un", "adjective", "Denoting a past period that was idyllically happy and peaceful.",
     "Buyers recall the halcyon days of 3% mortgages.", "Greek halkyōn, a mythical bird that calmed the seas."),
    ("inexorable", "in-EK-ser-uh-bul", "adjective", "Impossible to stop or prevent.",
     "The inexorable rise of sea levels threatens coastal property.", "Latin inexorabilis, 'not to be moved by entreaty'."),
    ("kleptocracy", "klep-TOK-ruh-see", "noun", "A government whose leaders steal from the people they govern.",
     "Sanctions targeted the regime's kleptocracy.", "Greek kleptēs 'thief' + -kratia 'rule'."),
    ("modicum", "MOD-i-kum", "noun", "A small quantity of something, especially something desirable.",
     "The ceasefire brought a modicum of relief.", "Latin modicus, 'moderate'."),
    ("nascent", "NAY-sunt", "adjective", "Just beginning to exist and showing signs of future potential.",
     "Quantum computing remains a nascent industry.", "Latin nasci, 'to be born'."),
    ("obsequious", "ub-SEE-kwee-us", "adjective", "Excessively eager to please or obey.",
     "Early chatbots were criticised as obsequious.", "Latin obsequiosus, from obsequi 'to comply'."),
    ("paradigm", "PAIR-uh-dime", "noun", "A typical model or pattern; a framework of ideas.",
     "Generative AI is shifting the paradigm of search.", "Greek paradeigma, 'pattern'."),
    ("rapprochement", "rap-rohsh-MAHN", "noun", "The re-establishment of cordial relations.",
     "The visit signalled a rapprochement between the neighbours.", "French, from rapprocher 'to bring together'."),
    ("specious", "SPEE-shus", "adjective", "Superficially plausible but actually wrong.",
     "The argument that rent control alone fixes affordability is specious.", "Latin speciosus, 'fair, plausible'."),
    ("tenuous", "TEN-yoo-us", "adjective", "Very weak or slight; insubstantial.",
     "The coalition's hold on power is tenuous.", "Latin tenuis, 'thin'."),
    ("ubiquitous", "yoo-BIK-wi-tus", "adjective", "Present, appearing, or found everywhere.",
     "Smartphones became ubiquitous within a decade.", "Latin ubique, 'everywhere'."),
    ("vicissitude", "vi-SIS-i-tood", "noun", "A change of circumstances, typically one that is unwelcome.",
     "Homeowners weathered the vicissitudes of the rate cycle.", "Latin vicissitudo, from vicis 'change'."),
    ("wonk", "WONK", "noun", "A person who takes an excessive interest in the minor details of policy.",
     "Housing wonks have long favoured zoning reform.", "American slang, origin uncertain (1920s)."),
    ("xenophobia", "zen-uh-FOH-bee-uh", "noun", "Dislike of or prejudice against people from other countries.",
     "The campaign was accused of stoking xenophobia.", "Greek xenos 'stranger' + phobos 'fear'."),
    ("zealot", "ZEL-ut", "noun", "A person who is fanatical in pursuit of their ideals.",
     "Even efficiency zealots admit some meetings matter.", "Greek zēlōtēs, 'emulator, admirer'."),
    ("apocryphal", "uh-POK-ruh-ful", "adjective", "Of doubtful authenticity, although widely circulated as true.",
     "The quote attributed to the founder is probably apocryphal.", "Greek apokryphos, 'hidden away'."),
    ("cadre", "KAD-ree", "noun", "A small group of people specially trained for a purpose.",
     "A cadre of engineers built the first prototype.", "French, 'frame', from Latin quadrum 'square'."),
    ("demagogue", "DEM-uh-gog", "noun", "A political leader who seeks support by appealing to prejudices rather than reason.",
     "Columnists warned of a demagogue's rise.", "Greek dēmagōgos, 'leader of the people'."),
    ("encroach", "en-KROHCH", "verb", "To intrude gradually on a person's territory, rights, or time.",
     "Suburbs continue to encroach on farmland.", "Old French encrochier, 'to seize, fasten upon'."),
    ("fungible", "FUN-juh-bul", "adjective", "Able to be replaced by another identical item; interchangeable.",
     "Unlike homes, dollars are perfectly fungible.", "Latin fungi, 'perform', in the sense 'perform in place of'."),
    ("gerrymander", "JAIR-ee-man-der", "verb", "To manipulate electoral boundaries to favour a party.",
     "The new map was gerrymandered to protect incumbents.", "Governor Elbridge Gerry + salamander, after an 1812 district shape."),
    ("histrionic", "his-tree-ON-ik", "adjective", "Overly theatrical or melodramatic.",
     "The senator's histrionic speech went viral.", "Latin histrio, 'actor'."),
    ("iconoclast", "eye-KON-uh-klast", "noun", "A person who attacks cherished beliefs or institutions.",
     "The economist built a career as an iconoclast.", "Greek eikōn 'image' + klastēs 'breaker'."),
    ("jejune", "juh-JOON", "adjective", "Naive and simplistic; also dull.",
     "The proposal struck critics as jejune.", "Latin jejunus, 'fasting, barren'."),
]


def word_for(day: date, used: set[str] | None = None) -> WordOfTheDay:
    """Rotate through the list by date, skipping recently used words."""
    used = used or set()
    for offset in range(len(WORDS)):
        entry = WORDS[(day.toordinal() + offset) % len(WORDS)]
        if entry[0] not in used:
            return WordOfTheDay(*entry)
    return WordOfTheDay(*WORDS[day.toordinal() % len(WORDS)])


def from_stories(stories: list[Story], used: set[str] | None = None) -> WordOfTheDay | None:
    """A list word that actually appears in one of today's stories, if any."""
    used = used or set()
    for story in stories:
        text = f"{story.title} {story.summary}".lower()
        for entry in WORDS:
            # Match inflections too: "exacerbated", "bellwethers".
            stem = entry[0][:-1] if len(entry[0]) > 6 else entry[0]
            if entry[0] not in used and re.search(rf"\b{re.escape(stem)}", text):
                word = WordOfTheDay(*entry)
                word.related_url, word.related_title = story.url, story.title
                word.theme = f"Spotted in today's {story.source} piece."
                return word
    return None
