"""
Insert calibration Phase 1 four-model analysis into the DB.
Run once after the calibration brief has been reviewed.
"""
import sqlite3, json, datetime, pathlib, sys

DB_PATH = pathlib.Path("data/corpus.db")

NARRATIVES = [
    # id, description, primary_domain, secondary_domain, tier, first_seen, last_seen
    ("N0001", "Gig/platform delivery workers face heat-stress mortality risk while platforms incentivise working through peak-heat hours, with no statutory wage protection.", "ECONOMIC", "SOCIAL", "T1", "2026-04-03", "2026-05-03"),
    ("N0002", "TCS-Nashik sexual-harassment complaints by nine women employees were progressively reframed by police, media, and NIA as a Muslim-led 'conversion racket', illustrating how communal framing supersedes workplace-rights framing.", "SOCIAL", "POLITICAL", "T1", "2026-04-03", "2026-05-03"),
    ("N0003", "West Bengal's Special Intensive Revision deleted 61+ lakh names from voter rolls with stark gender bias against Muslim and poor women, while appellate tribunals remained inaccessible.", "POLITICAL", "SOCIAL", "T3", "2026-04-03", "2026-05-03"),
    ("N0004", "India ranked 157/180 in the 2026 World Press Freedom Index; The Wire blocked by GoI; DPDP Act used to restrict RTI and journalist source protection.", "POLITICAL", "SOCIAL", "T3", "2026-04-03", "2026-05-03"),
    ("N0005", "UAPA invoked against a social media account (TeluguScribe) to compel X to hand over user data, extending anti-terror law into digital speech suppression.", "POLITICAL", "SOCIAL", "T1", "2026-04-03", "2026-05-03"),
    ("N0006", "AltNews ground reconstruction of the Jangipur/Murshidabad Ram Navami violence establishes a BJP-linked rally route as triggering communal attacks on Muslim homes and shops, contradicting official 'spontaneous clash' framing.", "SOCIAL", "POLITICAL", "T1", "2026-04-03", "2026-05-03"),
    ("N0007", "Three years after the Manipur ethnic violence, the commission of inquiry has not submitted findings; fresh killings and protests continue while the political settlement demand is unmet.", "POLITICAL", "SOCIAL", "T3", "2026-04-03", "2026-05-03"),
    ("N0008", "Bihar and Punjab migrant workers are returning home as 'LPG refugees'—cooking gas has become unaffordable in cities due to supply disruptions from the US-Iran war.", "ECONOMIC", "SOCIAL", "T2", "2026-04-03", "2026-05-03"),
    ("N0009", "Christian families in Odisha were prevented from burying their dead unless they renounced Christianity—an unreported coercive ghar-wapasi in practice.", "SOCIAL", "POLITICAL", "T2", "2026-04-03", "2026-05-03"),
    ("N0010", "A BSF soldier died in NCB custody; post-mortem indicates brutal torture—custodial death in a security agency never covered by mainstream media.", "POLITICAL", "SOCIAL", "T2", "2026-04-03", "2026-05-03"),
    ("N0011", "Indian pharma exporters (Syncom Formulations, linked to Gambia child deaths) continue operating with minimal regulatory consequence; tapentadol exports from India drive abuse crisis in Ghana.", "ECONOMIC", "SOCIAL", "T1", "2026-04-03", "2026-05-03"),
    ("N0012", "Indian authorities abandoned 40 Rohingya refugees at sea, violating non-refoulement; no mainstream coverage.", "POLITICAL", "SOCIAL", "T2", "2026-04-03", "2026-05-03"),
    ("N0013", "Workers and activists arrested in Noida violence; a Lucknow journalist arrested for 'conspiracy'; protest at Jantar Mantar calling for release.", "POLITICAL", "SOCIAL", "T2", "2026-04-03", "2026-05-03"),
    ("N0014", "Scheduled Caste ASHA Facilitator disabled and dismissed via caste discrimination when she became eligible for promotion; systemic caste exclusion in health workforce.", "SOCIAL", "ECONOMIC", "T1", "2026-04-03", "2026-05-03"),
    ("N0015", "Women farmers lack land titles and remain invisibilised in agricultural policy despite forming the backbone of India's farm labour.", "ECONOMIC", "SOCIAL", "T1", "2026-04-03", "2026-05-03"),
]

NARRATIVE_GROUPS = {
    "N0001": ["gig_workers", "sanitation_workers", "construction_workers", "migrants_internal"],
    "N0002": ["muslim_general", "women_formal", "prisoners_undertrial", "lawyers"],
    "N0003": ["muslim_general", "women_rural", "women_urban_informal", "pasmanda"],
    "N0004": ["journalists", "activists", "lawyers"],
    "N0005": ["journalists", "activists", "muslim_general"],
    "N0006": ["muslim_general", "pasmanda"],
    "N0007": ["manipuri", "kuki", "meitei"],
    "N0008": ["migrants_internal", "agri_labour", "farmers_small"],
    "N0009": ["christian", "dalit"],
    "N0010": ["activists", "prisoners_undertrial"],
    "N0011": ["children", "disabled"],
    "N0012": ["refugees", "undocumented", "muslim_general"],
    "N0013": ["workers_factory", "activists", "journalists"],
    "N0014": ["dalit", "women_rural", "asha_workers", "anganwadi_workers"],
    "N0015": ["women_rural", "farmers_small", "agri_labour"],
}

NARRATIVE_ANALYSIS = {
    "N0001": {
        "hc_filters_evaded": ["advertising", "sourcing", "ownership"],
        "hc_residual_filters": ["english_audience", "urban_skew", "platform_virality"],
        "mainstream_filter_most_at_play": "advertising",
        "ellul": {
            "propaganda_type": "SOCIOLOGICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "BOTH",
            "rational_or_irrational": "MIXED",
            "sociological_substrate": "motivational_influencer",
            "absent_sociological_field": "Aspirational startup-economy common sense (Swiggy/Zomato as India's digital success stories, gig economy as 'entrepreneurial opportunity') that makes platform precarity legible only as individual hustle-failure, not structural labour exploitation. The dominant grammar is the delivery-boy-who-became-entrepreneur success reel, which crowds out the worker-who-collapsed-from-heat-stroke reality."
        },
        "structural_depth": 5,
        "intersectional_count": 3
    },
    "N0002": {
        "hc_filters_evaded": ["sourcing", "fear_ideology", "flak"],
        "hc_residual_filters": ["legal_harassment_chill", "english_audience", "elite_informants"],
        "mainstream_filter_most_at_play": "fear_ideology",
        "ellul": {
            "propaganda_type": "MIXED",
            "agitation_or_integration": "AGITATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "IRRATIONAL",
            "sociological_substrate": "hindutva_developmentalist",
            "absent_sociological_field": "Crime-Patrol/detective-show grammar that normalises months of NIA/ATS interrogation as routine procedural necessity; Hindutva-developmentalist common sense where Muslim professionals in corporate India are presumptively suspect, making the NIA summons feel unremarkable rather than extraordinary. The workplace-rights story is dissolved by the conversion-racket thriller frame."
        },
        "structural_depth": 5,
        "intersectional_count": 3
    },
    "N0003": {
        "hc_filters_evaded": ["sourcing", "fear_ideology"],
        "hc_residual_filters": ["urban_skew", "delhi_mumbai_centrism", "subscriber_audience_bias"],
        "mainstream_filter_most_at_play": "sourcing",
        "ellul": {
            "propaganda_type": "POLITICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "constitutional_liberal",
            "absent_sociological_field": "Electoral-festival aestheticism — the spectacle of voting as national celebration (India's democracy, the world's largest) that makes the machinery of voter deletion feel like bureaucratic accident rather than political strategy. The photo-op of people holding up ink-stained fingers crowds out the story of those who could not vote."
        },
        "structural_depth": 4,
        "intersectional_count": 3
    },
    "N0004": {
        "hc_filters_evaded": ["ownership", "advertising", "fear_ideology"],
        "hc_residual_filters": ["subscriber_audience_bias", "platform_virality", "foundation_funding"],
        "mainstream_filter_most_at_play": "ownership",
        "ellul": {
            "propaganda_type": "POLITICAL",
            "agitation_or_integration": "BOTH",
            "direction": "BOTH",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "constitutional_liberal",
            "absent_sociological_field": "24-hour TRP-chasing television grammar that treats journalism as entertainment product (debate-show gladiators, anchor-as-celebrity), making the concept of press-as-Fourth-Estate feel archaic or niche. The structural collapse of press freedom is invisible inside a media environment that performs outrage daily."
        },
        "structural_depth": 4,
        "intersectional_count": 2
    },
    "N0005": {
        "hc_filters_evaded": ["fear_ideology", "sourcing"],
        "hc_residual_filters": ["legal_harassment_chill", "platform_virality"],
        "mainstream_filter_most_at_play": "fear_ideology",
        "ellul": {
            "propaganda_type": "POLITICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "constitutional_liberal",
            "absent_sociological_field": "Cybercrime-thriller grammar (the anonymous hacker as threat, the state as protector of digital order) that makes UAPA's application to a Twitter account feel like legitimate law enforcement rather than anti-terror law misapplied to speech. Tech-nationalism discourse further integrates state surveillance as 'national security'."
        },
        "structural_depth": 3,
        "intersectional_count": 2
    },
    "N0006": {
        "hc_filters_evaded": ["sourcing", "fear_ideology"],
        "hc_residual_filters": ["hindutva_secular_binary", "english_audience", "ngo_sourcing"],
        "mainstream_filter_most_at_play": "sourcing",
        "ellul": {
            "propaganda_type": "MIXED",
            "agitation_or_integration": "AGITATION",
            "direction": "BOTH",
            "rational_or_irrational": "IRRATIONAL",
            "sociological_substrate": "hindutva_cultural_revivalist",
            "absent_sociological_field": "Ram Navami processional aesthetics — the annual festival-march as legitimate community expression — that pre-authorizes rally routes through Muslim neighbourhoods as cultural right, making their use as communal provocation illegible within the mainstream Hindu-festival celebratory frame."
        },
        "structural_depth": 4,
        "intersectional_count": 2
    },
    "N0007": {
        "hc_filters_evaded": ["sourcing", "flak"],
        "hc_residual_filters": ["delhi_mumbai_centrism", "english_audience"],
        "mainstream_filter_most_at_play": "sourcing",
        "ellul": {
            "propaganda_type": "POLITICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "MIXED",
            "sociological_substrate": "military_nationalist",
            "absent_sociological_field": "North-East as imagined periphery — the cultural grammar of the Seven Sisters as frontier zone, exotic but distant — that makes prolonged ethnic violence in Manipur feel geographically remote and constitutionally exceptional, rather than a test of the Indian federal state's accountability to all citizens."
        },
        "structural_depth": 3,
        "intersectional_count": 3
    },
    "N0008": {
        "hc_filters_evaded": ["sourcing", "ownership", "advertising"],
        "hc_residual_filters": ["delhi_mumbai_centrism", "english_audience", "urban_skew"],
        "mainstream_filter_most_at_play": "sourcing",
        "ellul": {
            "propaganda_type": "SOCIOLOGICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "hindutva_developmentalist",
            "absent_sociological_field": "PM Ujjwala Yojana success-story grammar — the government's flagship LPG-to-rural-women scheme as development achievement — that makes the reversal (LPG unaffordable for migrant workers in cities) constitutionally impossible to absorb within official development narrative. The scheme celebrated on billboards cannot simultaneously be failing in practice."
        },
        "structural_depth": 4,
        "intersectional_count": 3
    },
    "N0009": {
        "hc_filters_evaded": ["fear_ideology", "sourcing"],
        "hc_residual_filters": ["legal_harassment_chill", "english_audience", "ngo_sourcing"],
        "mainstream_filter_most_at_play": "fear_ideology",
        "ellul": {
            "propaganda_type": "SOCIOLOGICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "IRRATIONAL",
            "sociological_substrate": "hindutva_cultural_revivalist",
            "absent_sociological_field": "Ghar Wapasi aesthetic grammar — reconversion as joyful homecoming, as cultural restoration — that makes coercive conversion via denial of burial rights invisible as coercion. The village-panchayat setting naturalises the pressure as community decision rather than rights violation."
        },
        "structural_depth": 4,
        "intersectional_count": 2
    },
    "N0010": {
        "hc_filters_evaded": ["sourcing", "flak", "fear_ideology"],
        "hc_residual_filters": ["legal_harassment_chill", "elite_informants"],
        "mainstream_filter_most_at_play": "fear_ideology",
        "ellul": {
            "propaganda_type": "POLITICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "military_nationalist",
            "absent_sociological_field": "Military-nationalist reverence grammar — the security forces as national guardian, beyond civilian accountability — that makes torture-in-custody by the NCB of a BSF soldier feel like an anomaly too embarrassing for official channels to address, and too uncomfortable for media to agitate about without appearing 'anti-security'."
        },
        "structural_depth": 4,
        "intersectional_count": 1
    },
    "N0011": {
        "hc_filters_evaded": ["advertising", "sourcing", "ownership"],
        "hc_residual_filters": ["english_audience", "ngo_sourcing", "foreign_funding"],
        "mainstream_filter_most_at_play": "advertising",
        "ellul": {
            "propaganda_type": "SOCIOLOGICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "BOTH",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "market_libertarian",
            "absent_sociological_field": "Make-in-India pharma-nationalism grammar (India as global pharmacy, generics for the world's poor) that makes regulatory failure of Indian export medicines abroad unpatriotic to raise. The 'brand India' pharmaceutical narrative makes the Gambia child-death scandal a foreign affairs inconvenience rather than a domestic regulatory accountability story."
        },
        "structural_depth": 4,
        "intersectional_count": 2
    },
    "N0012": {
        "hc_filters_evaded": ["fear_ideology", "sourcing"],
        "hc_residual_filters": ["foreign_funding", "english_audience"],
        "mainstream_filter_most_at_play": "fear_ideology",
        "ellul": {
            "propaganda_type": "POLITICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "IRRATIONAL",
            "sociological_substrate": "military_nationalist",
            "absent_sociological_field": "Infiltrator-security grammar — the Bangladeshi/Rohingya Muslim as threat to national integrity — that pre-frames any story of Rohingya at sea as a Border Security story (detection/deportation success), making the abandonment-at-sea a legal and moral non-event within mainstream common sense."
        },
        "structural_depth": 4,
        "intersectional_count": 2
    },
    "N0013": {
        "hc_filters_evaded": ["sourcing", "fear_ideology"],
        "hc_residual_filters": ["legal_harassment_chill", "platform_virality"],
        "mainstream_filter_most_at_play": "sourcing",
        "ellul": {
            "propaganda_type": "POLITICAL",
            "agitation_or_integration": "AGITATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "constitutional_liberal",
            "absent_sociological_field": "Law-and-order restoration grammar — the state cracking down on 'violence' as neutral civic duty — that absorbs the arrest of workers and a journalist into a public-safety story, making the political targeting of labour activists invisible within the mainstream 'violence was wrong' frame."
        },
        "structural_depth": 3,
        "intersectional_count": 2
    },
    "N0014": {
        "hc_filters_evaded": ["sourcing", "advertising", "ownership"],
        "hc_residual_filters": ["english_audience", "urban_skew", "ngo_sourcing"],
        "mainstream_filter_most_at_play": "sourcing",
        "ellul": {
            "propaganda_type": "SOCIOLOGICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "festival_aestheticist",
            "absent_sociological_field": "Festival-aestheticist culture that renders ASHA workers visible only as frontline-heroes during Covid (PPE-less warriors celebrated in WhatsApp forwards) and then invisible in routine professional life. The heroic-pandemic-worker grammar cannot accommodate the story of caste discrimination in a government health programme."
        },
        "structural_depth": 4,
        "intersectional_count": 3
    },
    "N0015": {
        "hc_filters_evaded": ["sourcing", "advertising", "ownership"],
        "hc_residual_filters": ["english_audience", "urban_skew", "delhi_mumbai_centrism"],
        "mainstream_filter_most_at_play": "sourcing",
        "ellul": {
            "propaganda_type": "SOCIOLOGICAL",
            "agitation_or_integration": "INTEGRATION",
            "direction": "VERTICAL",
            "rational_or_irrational": "RATIONAL",
            "sociological_substrate": "hindutva_developmentalist",
            "absent_sociological_field": "Agricultural achievement grammar — the 'annadata' (food-giver) nationalist framing of the male farmer as national provider — that renders the landless women who do most farm labour constitutionally illegible as rights-bearing subjects within agricultural policy discourse."
        },
        "structural_depth": 4,
        "intersectional_count": 3
    },
}

OUTLET_PROFILES = [
    {
        "source_id": "indiaspend",
        "framing_phrases": ["gig workers", "heat stress", "data shows", "according to govt data", "India has X million"],
        "register": "data-journalism, neutral-empirical",
        "state_axis": -1,
        "culture_axis": 0,
        "market_axis": -2,
        "ellul_profile": {"dominant_mode": "AGITATION", "direction": "VERTICAL", "type": "POLITICAL"},
        "heuristic_profile": {"dominant": "availability", "secondary": "authority", "fluency": 4, "affect": 2},
    },
    {
        "source_id": "article14",
        "framing_phrases": ["due process", "weaponised", "NIA", "UAPA", "custodial", "conversion racket"],
        "register": "legal-accountability, forensic-factual",
        "state_axis": -4,
        "culture_axis": 2,
        "market_axis": -1,
        "ellul_profile": {"dominant_mode": "AGITATION", "direction": "VERTICAL", "type": "POLITICAL"},
        "heuristic_profile": {"dominant": "moral_disgust", "secondary": "authority", "fluency": 3, "affect": 4},
    },
    {
        "source_id": "behanbox",
        "framing_phrases": ["structural barriers", "intersectional", "data show", "women farmers", "gender bias", "invisible"],
        "register": "feminist-data, activist-empirical",
        "state_axis": -3,
        "culture_axis": 4,
        "market_axis": -3,
        "ellul_profile": {"dominant_mode": "AGITATION", "direction": "BOTH", "type": "MIXED"},
        "heuristic_profile": {"dominant": "identifiable_victim", "secondary": "moral_disgust", "fluency": 4, "affect": 4},
    },
    {
        "source_id": "altnews",
        "framing_phrases": ["viral claim", "misleading", "false", "no cogniable offence", "fact check", "ground report"],
        "register": "fact-check, reactive-forensic",
        "state_axis": -2,
        "culture_axis": 2,
        "market_axis": 0,
        "ellul_profile": {"dominant_mode": "AGITATION", "direction": "HORIZONTAL", "type": "POLITICAL"},
        "heuristic_profile": {"dominant": "availability", "secondary": "source_credibility", "fluency": 4, "affect": 3},
    },
    {
        "source_id": "maktoob",
        "framing_phrases": ["Muslim community", "demolition", "press freedom", "minorities", "pilgrims", "Kashmir"],
        "register": "Muslim-community-beat, rights-focused",
        "state_axis": -4,
        "culture_axis": 3,
        "market_axis": -2,
        "ellul_profile": {"dominant_mode": "AGITATION", "direction": "BOTH", "type": "POLITICAL"},
        "heuristic_profile": {"dominant": "identifiable_victim", "secondary": "ingroup_outgroup", "fluency": 3, "affect": 4},
    },
    {
        "source_id": "pari",
        "framing_phrases": ["rural", "Adivasi", "farmer", "migrant worker", "village", "Bihar", "Bundelkhand"],
        "register": "vernacular-fieldwork, oral-archive",
        "state_axis": -2,
        "culture_axis": 3,
        "market_axis": -4,
        "ellul_profile": {"dominant_mode": "BOTH", "direction": "BOTH", "type": "SOCIOLOGICAL"},
        "heuristic_profile": {"dominant": "identifiable_victim", "secondary": "availability", "fluency": 5, "affect": 5},
    },
    {
        "source_id": "newslaundry",
        "framing_phrases": ["press freedom", "mainstream media", "subscriber-funded", "TV Newsance", "media criticism"],
        "register": "meta-media, subscriber-advocacy",
        "state_axis": -3,
        "culture_axis": 2,
        "market_axis": -1,
        "ellul_profile": {"dominant_mode": "AGITATION", "direction": "HORIZONTAL", "type": "POLITICAL"},
        "heuristic_profile": {"dominant": "ingroup_outgroup", "secondary": "source_credibility", "fluency": 4, "affect": 3},
    },
    {
        "source_id": "mongabay",
        "framing_phrases": ["forest diversion", "biodiversity", "climate", "wetland", "Adivasi", "wildlife"],
        "register": "science-journalism, conservation-advocacy",
        "state_axis": -2,
        "culture_axis": 2,
        "market_axis": -4,
        "ellul_profile": {"dominant_mode": "AGITATION", "direction": "VERTICAL", "type": "POLITICAL"},
        "heuristic_profile": {"dominant": "novelty", "secondary": "authority", "fluency": 4, "affect": 3},
    },
    {
        "source_id": "indianexpress",
        "framing_phrases": ["government says", "minister said", "official sources", "election results", "NITI Aayog", "Supreme Court"],
        "register": "institutional-liberal, access-journalism",
        "state_axis": 1,
        "culture_axis": 1,
        "market_axis": 1,
        "ellul_profile": {"dominant_mode": "INTEGRATION", "direction": "VERTICAL", "type": "POLITICAL"},
        "heuristic_profile": {"dominant": "authority", "secondary": "availability", "fluency": 4, "affect": 2},
    },
    {
        "source_id": "hindustantimes",
        "framing_phrases": ["police said", "BJP", "government announces", "EC orders", "Mamata", "security forces"],
        "register": "ownership-aligned, access-journalism",
        "state_axis": 3,
        "culture_axis": 0,
        "market_axis": 2,
        "ellul_profile": {"dominant_mode": "INTEGRATION", "direction": "VERTICAL", "type": "POLITICAL"},
        "heuristic_profile": {"dominant": "authority", "secondary": "bandwagon", "fluency": 4, "affect": 2},
    },
]

STRUCTURAL_SYMMETRIES = [
    {
        "event_description": "TCS Nashik case: 9 women employees file sexual harassment complaint. AltNews and Article14 report on how the official/mainstream frame became 'conversion racket'; mainstream covered court proceedings using NIA/police sourcing.",
        "finding": "Independent items (Article14, Sukanya Shantha) use 'workplace harassment', 'due process', 'NIA weaponisation' framing. Mainstream items (HT court note) use 'conversion racket', 'bail denied' without interrogating the escalation mechanics. Both sets of items use the identifiable_victim heuristic — but the victim flips: independent coverage centres the 9 complainants; mainstream coverage centres the accused's supposed victims of 'forced conversion'. Identical heuristic structure; opposite factual referent. NOTE: this symmetry is heuristic, not factual — the 9 harassment complaints are documented; the 'conversion racket' narrative is not.",
    },
    {
        "event_description": "West Bengal election season: EC orders repoll after voter deletions. BehanBox/Wire report structural deletion of women/minorities; mainstream reports repoll order as EC corrective action.",
        "finding": "Both independent and mainstream coverage uses the authority heuristic (EC decisions as definitive). Independent coverage adds availability heuristic through named affected individuals (91 lakh voters, named testimonies). Mainstream frames EC repoll as system working; independent frames voter deletion as system failing then partially correcting. Same event, opposite verdict on institutional function. NOTE: the 61 lakh deletion figure is documented by BehanBox via RTI data; the mainstream 'repoll = correction' frame does not engage with the deletion pattern.",
    },
]


def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    # Insert narratives
    for n in NARRATIVES:
        nid, desc, pd, sd, tier, fs, ls = n
        conn.execute(
            """INSERT OR REPLACE INTO narratives
               (id, description, primary_domain, secondary_domain, tier, first_seen, last_seen, created_at)
               VALUES (?,?,?,?,?,?,?,datetime('now'))""",
            (nid, desc, pd, sd, tier, fs, ls),
        )
        print(f"[db] narrative {nid} inserted")

    # Insert narrative groups
    for nid, groups in NARRATIVE_GROUPS.items():
        for g in groups:
            conn.execute(
                "INSERT OR IGNORE INTO narrative_groups (narrative_id, group_tag) VALUES (?,?)",
                (nid, g),
            )

    # Insert narrative analysis
    for nid, an in NARRATIVE_ANALYSIS.items():
        conn.execute(
            """INSERT OR REPLACE INTO narrative_analysis
               (narrative_id, hc_filters_evaded, hc_residual_filters, ellul,
                structural_depth, intersectional_count, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                nid,
                json.dumps(an["hc_filters_evaded"]),
                json.dumps(an["hc_residual_filters"]),
                json.dumps(an["ellul"], ensure_ascii=False),
                an["structural_depth"],
                an["intersectional_count"],
                now_iso(),
            ),
        )
        print(f"[db] narrative_analysis {nid} inserted")

    # Also store mainstream_filter_most_at_play in narratives table
    for nid, an in NARRATIVE_ANALYSIS.items():
        conn.execute(
            "UPDATE narratives SET mainstream_filter_most_at_play=? WHERE id=?",
            (an["mainstream_filter_most_at_play"], nid),
        )

    # Insert outlet profiles
    for op in OUTLET_PROFILES:
        conn.execute(
            """INSERT OR REPLACE INTO outlet_profile
               (source_id, framing_phrases, register, state_axis, culture_axis, market_axis,
                ellul_profile, heuristic_profile, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                op["source_id"],
                json.dumps(op["framing_phrases"]),
                op["register"],
                op["state_axis"],
                op["culture_axis"],
                op["market_axis"],
                json.dumps(op["ellul_profile"]),
                json.dumps(op["heuristic_profile"]),
                now_iso(),
            ),
        )
        print(f"[db] outlet_profile {op['source_id']} inserted")

    # Insert structural symmetries
    for ss in STRUCTURAL_SYMMETRIES:
        conn.execute(
            """INSERT INTO structural_symmetries
               (event_description, finding, created_at)
               VALUES (?,?,datetime('now'))""",
            (ss["event_description"], ss["finding"]),
        )
        print(f"[db] structural_symmetry inserted")

    conn.commit()
    conn.close()
    print("\n[db] All calibration data committed.")

    # Final stats
    conn2 = sqlite3.connect(DB_PATH)
    print(f"[db] narratives: {conn2.execute('SELECT COUNT(*) FROM narratives').fetchone()[0]}")
    print(f"[db] narrative_analysis: {conn2.execute('SELECT COUNT(*) FROM narrative_analysis').fetchone()[0]}")
    print(f"[db] outlet_profiles: {conn2.execute('SELECT COUNT(*) FROM outlet_profile').fetchone()[0]}")
    print(f"[db] structural_symmetries: {conn2.execute('SELECT COUNT(*) FROM structural_symmetries').fetchone()[0]}")
    conn2.close()


if __name__ == "__main__":
    main()
