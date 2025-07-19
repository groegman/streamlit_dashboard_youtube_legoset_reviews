import sqlite3
import json
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaLLM

# 🔹 Aktuellen Ollama LLM initialisieren
llm = OllamaLLM(model="llama3.2")  # Modell ggf. anpassen

# 🔹 Prompt mit Bewertung + Sponsoring-Erkennung
prompt = PromptTemplate.from_template("""
You are an expert LEGO review analyst. Your task is to classify YouTube LEGO review transcripts. Focus on the *sentiment of the review* and whether the set was likely *provided for free by LEGO*.

Your goals:

---

### 1. **Review Sentiment Classification**

Classify the overall sentiment into one of four strictly defined categories based only on what is said in the transcript.

- "strongly positive": Clear recommendation, enthusiastic praise, almost no criticism.
- "slightly positive": Mostly positive with some reservations or minor criticism.
- "slightly negative": Neutral or mixed impression with notable criticism.
- "strongly negative": Reviewer discourages purchase or expresses strong disappointment.
                                      
Also provide a `confidence_score` between 0 and 100 that reflects how confident you are in the sentiment classification.


---

### 2. **Sponsorship Detection**

Decide whether the reviewer received the LEGO set for free. Mark `sponsored` as **true** if *any part* of the transcript suggests the set was:
- gifted or sent early by LEGO,
- provided through the LEGO Ambassador Network (LAN),
- reviewed in collaboration with LEGO.

Examples of phrases that **must be marked `true`**:
- "Thanks to LEGO for sending this set"
- "This set was provided by LEGO"
- "Review copy provided by LEGO"
- "Sent early through the LAN"
- "LEGO asked me to review this"

Even **subtle or indirect** indications of a free product should be interpreted as `sponsored: true`.

If there is **no indication at all**, mark `sponsored: false`.

---

### Examples:

#### Example 1:
Transcript:
"I picked this set up at the LEGO store on day one, had to get it because of that dragon!"

→
```json
{{
  "review_category": "strongly positive",
  "review_rationale": "The reviewer shows clear excitement and purchased the set themselves.",
  "confidence_score": 98,                                      
  "sponsored": false
}}
```

#### Example 2:
Transcript:
"LEGO sent me this set to review—huge thanks to them for letting me build it early. Personally I think the colours are a bit outdated but other than that it is a really solid set."

→
```json
{{
  "review_category": "slightly positive",
  "review_rationale": "The reviewer appreciates the set, mentions flaws, and confirms it was provided by LEGO.",
  "confidence_score": 97,
  "sponsored": true
}}
```

#### Example 3:
Transcript:
"Some parts felt off to me. The dragon build was kind of clunky, but the mech is solid."

→
```json
{{
  "review_category": "slightly negative",
  "review_rationale": "Balanced tone with notable criticism about the dragon and praise for the mech.",
  "confidence_score": 95,
  "sponsored": false
}}
```
#### Example 4:
Transcript:
"hmm"

→
```json
{{
  "review_category": "slightly negative",
  "review_rationale": "There is only a very short transcript indicating an ambivalence",
  "confidence_score": 35,                                      
  "sponsored": false
}}
```

Now analyze the following transcript:
**Transcript**:
"{transcript}"

---

Return a response **strictly in this JSON format**:

{{
  "review_category": "<one of: strongly positive, slightly positive, slightly negative, strongly negative>",
  "review_rationale": "<short explanation in English>",
  "confidence_score": <value from 0 to 100>,  
  "sponsored": true or false
}}

Do not include any other commentary or text. Respond only with a valid JSON object.
""")

# 🔹 Moderne LangChain-Kette
chain = prompt | llm

# 🔹 Verbindung zur SQLite-Datenbank
conn = sqlite3.connect("data/lego_reviews.db")
cursor = conn.cursor()

# 🔹 Spalten in video_details prüfen und ggf. ergänzen
required_columns = {
    "review_category": "TEXT",
    "review_rationale": "TEXT",
    "confidence_score": "INTEGER",
    "sponsored": "BOOLEAN",
    "transcript_word_count": "INTEGER",
    "transcript_char_length": "INTEGER"
}

cursor.execute("PRAGMA table_info(video_details)")
existing_columns = {row[1] for row in cursor.fetchall()}

for column, coltype in required_columns.items():
    if column not in existing_columns:
        print(f"➕ Spalte '{column}' wird zur Tabelle 'video_details' hinzugefügt...")
        cursor.execute(f"ALTER TABLE video_details ADD COLUMN {column} {coltype}")
conn.commit()

# 🔹 Hole bis zu 3 unklassifizierte Transkripte
cursor.execute("""
    SELECT v.video_id, v.title, d.transcript
    FROM videos v
    JOIN video_details d ON v.video_id = d.video_id
    WHERE d.review_category IS NULL AND d.transcript IS NOT NULL
    LIMIT 50
""")
rows = cursor.fetchall()

# 🔹 Übersicht aller geladenen Videos
print("\n📋 Geladene Videos mit Transkript:\n")
for idx, (video_id, title, _) in enumerate(rows, start=1):
    print(f"{idx}. {title} (ID: {video_id})")

if not rows:
    print("\n❗ Keine unklassifizierten Transkripte gefunden.")
else:
    print("\n🚀 Starte Analyse...\n")

    for idx, (video_id, title, transcript) in enumerate(rows, start=1):
        print("=" * 80)
        print(f"🔍 Video {idx}: {title}")
        print(f"🆔 ID: {video_id}\n")

        clean_transcript = transcript.strip()
        char_length = len(clean_transcript)
        word_count = len(clean_transcript.split())

        print("📝 Transkript-Auszug:")
        print(clean_transcript[:500] + ("..." if len(clean_transcript) > 500 else ""))
        print(f"\n🧮 Länge des Transkripts: {char_length} Zeichen / {word_count} Wörter")

        if char_length < 100:
            print("⚠️ Transkript ist sehr kurz – möglicherweise nicht aussagekräftig.")

        try:
            result = chain.invoke({"transcript": clean_transcript})

            # Falls das Modell einen JSON-String liefert, parsen
            if isinstance(result, str):
                result = json.loads(result)

            print("\n✅ Strukturierte JSON-Antwort:")
            print(json.dumps(result, indent=2, ensure_ascii=False))

            # 🔹 Werte extrahieren
            review_category = result.get("review_category")
            review_rationale = result.get("review_rationale")
            confidence_score = result.get("confidence_score")
            sponsored = result.get("sponsored")

            if review_category and review_rationale is not None and confidence_score is not None and sponsored is not None:
                # 🔸 In Tabelle video_details schreiben
                cursor.execute("""
                    UPDATE video_details
                    SET review_category = ?, review_rationale = ?, confidence_score = ?, sponsored = ?, transcript_word_count = ?, transcript_char_length = ?
                    WHERE video_id = ?
                """, (review_category, review_rationale, int(confidence_score), int(sponsored), word_count, char_length, video_id))
                conn.commit()

                print(f"\n💾 Datenbank aktualisiert für Video {video_id}")
            else:
                print("⚠️ LLM-Antwort war unvollständig – nichts gespeichert.")

        except json.JSONDecodeError:
            print("\n⚠️ Antwort war kein gültiges JSON.")
            print("Antwort:")
            print(result)
        except Exception as e:
            print(f"\n❌ Fehler bei Analyse von {video_id}: {e}")

        print("\n")
