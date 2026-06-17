# -*- coding: utf-8 -*-
"""
keywords.py — All query-router keywords, grouped by language.

Every supported language now has a translation for every English concept, so
routing works consistently no matter which language a student uses.

LANGUAGE SCOPE (21) — bounded by ElevenLabs eleven_multilingual_v2 (TTS):
  en English  es Spanish  pt Portuguese  fr French  de German  it Italian
  ru Russian  uk Ukrainian  pl Polish  el Greek  nl Dutch  sv Swedish
  tr Turkish  zh Chinese  tl Tagalog  hi Hindi  ta Tamil  ko Korean
  ja Japanese  ar Arabic  he Hebrew

NOT supported by the voice pipeline (excluded): Haitian Creole, Gaelic,
Vietnamese, Gujarati, Telugu, Urdu, Bengali, Punjabi, Thai, Lao, Hmong, Khmer,
Persian, Amharic, Somali, Yoruba, Swahili, Mikasuki, Creek.

Note: proper nouns (institute names like "dendritic", "eaglecybernest") stay in
English across all languages because they are not translated terms.
"""

LANGS = ["en","es","pt","fr","de","it","ru","uk","pl","el","nl","sv",
         "tr","zh","tl","hi","ta","ko","ja","ar","he"]

# ── Learning Hub / tutoring / academic help  →  learning_support ──
HELP_WORDS = {
    "en": ["learning hub", "tutor", "tutoring", "get help", "help with classes",
           "academic support", "peer mentor", "fellows", "study help"],
    "es": ["centro de aprendizaje", "tutor", "tutoría", "obtener ayuda",
           "ayuda con las clases", "apoyo académico", "mentor", "becarios",
           "ayuda de estudio"],
    "pt": ["centro de aprendizagem", "tutor", "tutoria", "obter ajuda",
           "ajuda com as aulas", "apoio acadêmico", "mentor", "bolsistas",
           "ajuda nos estudos"],
    "fr": ["centre d'apprentissage", "tuteur", "tutorat", "obtenir de l'aide",
           "aide pour les cours", "soutien scolaire", "mentor", "moniteurs",
           "aide aux études"],
    "de": ["lernzentrum", "tutor", "nachhilfe", "hilfe bekommen",
           "hilfe bei kursen", "akademische unterstützung", "mentor",
           "tutoren", "lernhilfe"],
    "it": ["centro di apprendimento", "tutor", "tutoraggio", "ottenere aiuto",
           "aiuto con i corsi", "supporto accademico", "mentore", "borsisti",
           "aiuto allo studio"],
    "ru": ["учебный центр", "репетитор", "репетиторство", "получить помощь",
           "помощь с занятиями", "академическая поддержка", "наставник",
           "стипендиаты", "помощь в учебе"],
    "uk": ["навчальний центр", "репетитор", "репетиторство", "отримати допомогу",
           "допомога із заняттями", "академічна підтримка", "наставник",
           "стипендіати", "допомога в навчанні"],
    "pl": ["centrum nauki", "korepetytor", "korepetycje", "uzyskać pomoc",
           "pomoc z zajęciami", "wsparcie akademickie", "mentor",
           "stypendyści", "pomoc w nauce"],
    "el": ["κέντρο μάθησης", "δάσκαλος", "φροντιστήριο", "λάβετε βοήθεια",
           "βοήθεια με τα μαθήματα", "ακαδημαϊκή υποστήριξη", "μέντορας",
           "υπότροφοι", "βοήθεια μελέτης"],
    "nl": ["leercentrum", "bijlesdocent", "bijles", "hulp krijgen",
           "hulp bij vakken", "academische ondersteuning", "mentor",
           "studenten-assistenten", "studiehulp"],
    "sv": ["lärcentrum", "handledare", "handledning", "få hjälp",
           "hjälp med kurser", "akademiskt stöd", "mentor",
           "stipendiater", "studiehjälp"],
    "tr": ["öğrenme merkezi", "özel öğretmen", "özel ders", "yardım almak",
           "derslerde yardım", "akademik destek", "mentor",
           "öğrenci asistanları", "çalışma yardımı"],
    "zh": ["学习中心", "辅导员", "辅导", "获得帮助",
           "课程帮助", "学业支持", "导师", "助学金学生", "学习帮助"],
    "tl": ["learning hub", "tutor", "tutoring", "humingi ng tulong",
           "tulong sa mga klase", "akademikong suporta", "mentor",
           "fellows", "tulong sa pag-aaral"],
    "hi": ["लर्निंग हब", "ट्यूटर", "ट्यूशन", "मदद पाना",
           "कक्षाओं में मदद", "शैक्षणिक सहायता", "मार्गदर्शक",
           "फेलो", "अध्ययन सहायता"],
    "ta": ["கற்றல் மையம்", "பயிற்றுவிப்பாளர்", "பயிற்சி", "உதவி பெறு",
           "வகுப்புகளுக்கு உதவி", "கல்வி ஆதரவு", "வழிகாட்டி",
           "உதவியாளர்கள்", "படிப்பு உதவி"],
    "ko": ["학습 센터", "튜터", "튜터링", "도움 받기",
           "수업 도움", "학업 지원", "멘토", "펠로우", "학습 도움"],
    "ja": ["学習センター", "チューター", "個別指導", "助けを得る",
           "授業の手伝い", "学業支援", "メンター", "フェロー", "学習支援"],
    "ar": ["مركز التعلم", "مدرس خصوصي", "دروس خصوصية", "الحصول على مساعدة",
           "مساعدة في الفصول", "الدعم الأكاديمي", "مرشد", "زملاء",
           "مساعدة الدراسة"],
    "he": ["מרכז למידה", "מרכז הלמידה", "מורה פרטי", "שיעור פרטי", "לקבל עזרה",
           "עזרה בשיעורים", "תמיכה אקדמית", "מנטור", "עמיתים", "עזרה בלימודים"],
}

# Phrases that FORCE the learning-support route over everything else
LEARNING_HUB_OVERRIDE = {
    "en": ["learning hub", "learning center"],
    "es": ["centro de aprendizaje", "centro de estudios"],
    "pt": ["centro de aprendizagem", "centro de estudos"],
    "fr": ["centre d'apprentissage", "centre d'études"],
    "de": ["lernzentrum", "lernhilfezentrum"],
    "it": ["centro di apprendimento", "centro studi"],
    "ru": ["учебный центр", "центр обучения"],
    "uk": ["навчальний центр", "центр навчання"],
    "pl": ["centrum nauki", "centrum uczenia"],
    "el": ["κέντρο μάθησης", "κέντρο εκμάθησης"],
    "nl": ["leercentrum", "studiecentrum"],
    "sv": ["lärcentrum", "studiecentrum"],
    "tr": ["öğrenme merkezi", "öğrenim merkezi"],
    "zh": ["学习中心", "学习辅导中心"],
    "tl": ["learning hub", "learning center"],
    "hi": ["लर्निंग हब", "लर्निंग सेंटर"],
    "ta": ["கற்றல் மையம்", "கல்வி மையம்"],
    "ko": ["학습 센터", "러닝 허브"],
    "ja": ["学習センター", "ラーニングハブ"],
    "ar": ["مركز التعلم", "مركز التعليم"],
    "he": ["מרכז למידה", "מרכז הלמידה"],
}

# ── Course schedule (who/when/what time)  →  course_offering ──
SCHEDULE_WORDS = {
    "en": ["teach", "who teaches", "what time", "when does", "meet",
           "instructor", "crn", "schedule", "offered in"],
    "es": ["enseña", "imparte", "dicta", "quién enseña", "qué hora", "cuándo es",
           "se reúne", "instructor", "crn", "horario", "se ofrece en"],
    "pt": ["ensina", "leciona", "dá aula", "quem ensina", "que horas", "quando é",
           "encontra", "instrutor", "crn", "horário", "oferecido em"],
    "fr": ["enseigne", "qui enseigne", "quelle heure", "quand a lieu",
           "se réunit", "instructeur", "crn", "horaire", "offert en"],
    "de": ["lehrt", "unterrichtet", "wer unterrichtet", "uhrzeit", "wann findet", "trifft sich",
           "dozent", "crn", "stundenplan", "angeboten im"],
    "it": ["insegna", "chi insegna", "che ora", "quando si tiene", "si riunisce",
           "istruttore", "crn", "orario", "offerto in"],
    "ru": ["преподает", "кто ведет", "во сколько", "когда проходит",
           "встречается", "преподаватель", "crn", "расписание", "предлагается в"],
    "uk": ["викладає", "хто веде", "о котрій", "коли відбувається",
           "зустрічається", "викладач", "crn", "розклад", "пропонується в"],
    "pl": ["uczy", "kto prowadzi", "o której", "kiedy się odbywa",
           "spotyka się", "prowadzący", "crn", "harmonogram", "oferowany w"],
    "el": ["διδάσκει", "ποιος διδάσκει", "τι ώρα", "πότε γίνεται",
           "συναντιέται", "εκπαιδευτής", "crn", "πρόγραμμα", "προσφέρεται σε"],
    "nl": ["geeft les", "doceert", "wie geeft les", "hoe laat", "wanneer is",
           "komt samen", "docent", "crn", "rooster", "aangeboden in"],
    "sv": ["undervisar", "vem undervisar", "vilken tid", "när äger",
           "träffas", "instruktör", "crn", "schema", "erbjuds i"],
    "tr": ["öğretir", "veriyor", "okutuyor", "kim veriyor", "saat kaçta",
           "ne zaman", "buluşuyor", "eğitmen", "crn", "ders programı", "veriliyor"],
    "zh": ["教", "谁教", "什么时间", "什么时候", "上课地点",
           "讲师", "crn", "课表", "开课"],
    "tl": ["nagtuturo", "sino nagtuturo", "anong oras", "kailan",
           "nagkikita", "instruktor", "crn", "iskedyul", "inaalok sa"],
    "hi": ["पढ़ाता", "पढ़ाते", "कौन पढ़ाता", "किस समय", "कब होती", "मिलते",
           "प्रशिक्षक", "crn", "समय सारणी", "में दी जाती"],
    "ta": ["கற்பிக்கிறார்", "யார் கற்பிக்கிறார்", "எந்த நேரம்", "எப்போது",
           "சந்திக்கிறது", "பயிற்றுநர்", "crn", "அட்டவணை", "வழங்கப்படுகிறது"],
    "ko": ["가르치", "누가 가르치", "몇 시", "언제", "모이",
           "강사", "crn", "시간표", "개설"],
    "ja": ["教える", "誰が教える", "担当", "何時", "いつ", "集まる",
           "講師", "crn", "時間割", "開講"],
    "ar": ["يدرّس", "من يدرّس", "في أي وقت", "متى", "يجتمع",
           "مدرب", "crn", "الجدول", "يُقدّم في"],
    "he": ["מלמד", "מי מלמד", "באיזו שעה", "מתי", "נפגש",
           "מדריך", "crn", "מערכת שעות", "מוצע ב"],
}

# ── Course description (what it covers)  →  course_description ──
DESCRIPTION_WORDS = {
    "en": ["about", "cover", "describe", "description", "what is", "topics",
           "learn in", "content of"],
    "es": ["se trata", "cubre", "describe", "descripción", "qué es", "temas",
           "se aprende en", "contenido de"],
    "pt": ["sobre", "aborda", "descreve", "descrição", "o que é", "tópicos",
           "aprende em", "conteúdo de"],
    "fr": ["à propos", "couvre", "décrire", "description", "qu'est-ce",
           "sujets", "apprend en", "contenu de"],
    "de": ["worum geht", "behandelt", "beschreiben", "beschreibung", "was ist",
           "themen", "lernt man in", "inhalt von"],
    "it": ["di cosa", "tratta", "descrivere", "descrizione", "cos'è",
           "argomenti", "si impara in", "contenuto di"],
    "ru": ["о чем", "охватывает", "описать", "описание", "что это",
           "темы", "изучают в", "содержание"],
    "uk": ["про що", "охоплює", "описати", "опис", "що це",
           "теми", "вивчають у", "зміст"],
    "pl": ["o czym", "obejmuje", "opisać", "opis", "co to",
           "tematy", "uczy się na", "zawartość"],
    "el": ["σχετικά", "καλύπτει", "περιγράψτε", "περιγραφή", "τι είναι",
           "θέματα", "μαθαίνεις στο", "περιεχόμενο"],
    "nl": ["waarover", "behandelt", "beschrijven", "beschrijving", "wat is",
           "onderwerpen", "leer je in", "inhoud van"],
    "sv": ["handlar om", "täcker", "beskriv", "beskrivning", "vad är",
           "ämnen", "lär man sig i", "innehåll i"],
    "tr": ["hakkında", "kapsar", "açıkla", "açıklama", "nedir",
           "konular", "öğrenilir", "içeriği"],
    "zh": ["关于", "涵盖", "描述", "说明", "是什么",
           "主题", "学到", "内容"],
    "tl": ["tungkol sa", "saklaw", "ilarawan", "paglalarawan", "ano ang",
           "mga paksa", "natututunan sa", "nilalaman ng"],
    "hi": ["के बारे में", "किस बारे में", "शामिल", "वर्णन", "विवरण", "क्या है",
           "विषय", "सीखते हैं", "सामग्री"],
    "ta": ["பற்றி", "உள்ளடக்கம்", "விவரி", "விளக்கம்", "என்ன",
           "தலைப்புகள்", "கற்றுக்கொள்வது", "உள்ளடக்கம்"],
    "ko": ["에 대해", "다루", "설명", "설명서", "무엇", "주제",
           "배우", "내용"],
    "ja": ["について", "扱う", "説明", "概要", "とは", "トピック",
           "学ぶ", "内容"],
    "ar": ["حول", "يغطي", "صف", "وصف", "ما هو", "مواضيع",
           "تتعلم في", "محتوى"],
    "he": ["על מה", "מכסה", "תאר", "תיאור", "מה זה", "נושאים",
           "לומדים ב", "תוכן"],
}

# ── Curriculum / degree map  →  degree_map ──
CURRICULUM_WORDS = {
    "en": ["junior year", "senior year", "sophomore", "freshman",
           "concentration", "degree map", "what classes", "what courses",
           "requirements", "curriculum", "combined degree", "bs/ms",
           "do i need", "year in"],
    "es": ["tercer año", "cuarto año", "segundo año", "primer año",
           "concentración", "mapa de grado", "qué clases", "qué cursos",
           "requisitos", "plan de estudios", "título combinado", "bs/ms",
           "necesito", "año en"],
    "pt": ["terceiro ano", "quarto ano", "segundo ano", "primeiro ano",
           "concentração", "mapa do curso", "quais aulas", "quais cursos",
           "requisitos", "currículo", "diploma combinado", "bs/ms",
           "preciso", "ano em"],
    "fr": ["troisième année", "quatrième année", "deuxième année",
           "première année", "concentration", "plan de diplôme", "quelles classes",
           "quels cours", "exigences", "programme", "diplôme combiné", "bs/ms",
           "ai-je besoin", "année en"],
    "de": ["drittes jahr", "viertes jahr", "zweites jahr", "erstes jahr",
           "vertiefung", "studienplan", "welche klassen", "welche kurse",
           "voraussetzungen", "lehrplan", "kombinierter abschluss", "bs/ms",
           "brauche ich", "jahr in"],
    "it": ["terzo anno", "quarto anno", "secondo anno", "primo anno",
           "indirizzo", "piano di laurea", "quali classi", "quali corsi",
           "requisiti", "piano di studi", "laurea combinata", "bs/ms",
           "ho bisogno", "anno in"],
    "ru": ["третий курс", "четвертый курс", "второй курс", "первый курс",
           "специализация", "учебный план", "какие классы", "какие курсы",
           "требования", "программа обучения", "совмещенная степень", "bs/ms",
           "мне нужно", "год обучения"],
    "uk": ["третій курс", "четвертий курс", "другий курс", "перший курс",
           "спеціалізація", "навчальний план", "які класи", "які курси",
           "вимоги", "програма навчання", "поєднаний ступінь", "bs/ms",
           "мені потрібно", "рік навчання"],
    "pl": ["trzeci rok", "czwarty rok", "drugi rok", "pierwszy rok",
           "specjalizacja", "plan studiów", "jakie klasy", "jakie kursy",
           "wymagania", "program studiów", "łączony stopień", "bs/ms",
           "czy potrzebuję", "rok na"],
    "el": ["τρίτο έτος", "τέταρτο έτος", "δεύτερο έτος", "πρώτο έτος",
           "κατευθύνσεις", "χάρτης πτυχίου", "ποιες τάξεις", "ποια μαθήματα",
           "απαιτήσεις", "πρόγραμμα σπουδών", "συνδυασμένο πτυχίο", "bs/ms",
           "χρειάζομαι", "έτος σε"],
    "nl": ["derde jaar", "vierde jaar", "tweede jaar", "eerste jaar",
           "specialisatie", "diplomaplan", "welke klassen", "welke vakken",
           "vereisten", "studieprogramma", "gecombineerde graad", "bs/ms",
           "heb ik nodig", "jaar in"],
    "sv": ["tredje året", "fjärde året", "andra året", "första året",
           "inriktning", "examensplan", "vilka klasser", "vilka kurser",
           "krav", "studieplan", "kombinerad examen", "bs/ms",
           "behöver jag", "år i"],
    "tr": ["üçüncü yıl", "dördüncü yıl", "ikinci yıl", "birinci yıl",
           "uzmanlık", "derece haritası", "hangi sınıflar", "hangi dersler",
           "gereksinimler", "müfredat", "birleşik derece", "bs/ms",
           "ihtiyacım var", "yılında"],
    "zh": ["大三", "大四", "大二", "大一",
           "专业方向", "学位地图", "哪些班级", "哪些课程",
           "要求", "课程计划", "联合学位", "bs/ms",
           "我需要", "学年"],
    "tl": ["ikatlong taon", "ikaapat na taon", "ikalawang taon", "unang taon",
           "konsentrasyon", "degree map", "anong mga klase", "anong mga kurso",
           "mga kinakailangan", "kurikulum", "pinagsamang degree", "bs/ms",
           "kailangan ko ba", "taon sa"],
    "hi": ["तीसरा वर्ष", "चौथा वर्ष", "दूसरा वर्ष", "पहला वर्ष",
           "विशेषज्ञता", "डिग्री मानचित्र", "कौन सी कक्षाएं", "कौन से कोर्स",
           "आवश्यकताएं", "पाठ्यक्रम", "संयुक्त डिग्री", "bs/ms",
           "मुझे चाहिए", "वर्ष में"],
    "ta": ["மூன்றாம் ஆண்டு", "நான்காம் ஆண்டு", "இரண்டாம் ஆண்டு", "முதல் ஆண்டு",
           "செறிவு", "பட்டப் படிப்பு வரைபடம்", "எந்த வகுப்புகள்", "எந்த படிப்புகள்",
           "தேவைகள்", "பாடத்திட்டம்", "இணைந்த பட்டம்", "bs/ms",
           "எனக்கு தேவையா", "ஆண்டில்"],
    "ko": ["3학년", "4학년", "2학년", "1학년",
           "전공", "학위 과정", "어떤 수업", "어떤 과목",
           "요구 사항", "교육 과정", "복합 학위", "bs/ms",
           "필요한가요", "학년에"],
    "ja": ["3年生", "4年生", "2年生", "1年生",
           "専攻", "学位マップ", "どのクラス", "どの科目",
           "必要条件", "カリキュラム", "複合学位", "bs/ms",
           "必要ですか", "年に"],
    "ar": ["السنة الثالثة", "السنة الرابعة", "السنة الثانية", "السنة الأولى",
           "تخصص", "خريطة الدرجة", "ما الفصول", "ما المقررات",
           "المتطلبات", "المنهج", "درجة مشتركة", "bs/ms",
           "هل أحتاج", "سنة في"],
    "he": ["שנה שלישית", "שנה רביעית", "שנה שנייה", "שנה ראשונה",
           "התמחות", "מפת תואר", "אילו שיעורים", "אילו קורסים",
           "דרישות", "תכנית לימודים", "תואר משולב", "bs/ms",
           "אני צריך", "בשנה ה"],
}

# ── Faculty  →  faculty + faculty_reviews ──
FACULTY_WORDS = {
    "en": ["professor", "faculty", "who are the"],
    "es": ["profesor", "facultad", "quiénes son los"],
    "pt": ["professor", "corpo docente", "quem são os"],
    "fr": ["professeur", "faculté", "qui sont les"],
    "de": ["professor", "lehrkräfte", "wer sind die"],
    "it": ["professore", "facoltà", "chi sono i"],
    "ru": ["профессор", "преподаватели", "кто такие"],
    "uk": ["професор", "викладачі", "хто такі"],
    "pl": ["profesor", "wykładowcy", "kim są"],
    "el": ["καθηγητής", "διδακτικό προσωπικό", "ποιοι είναι οι"],
    "nl": ["professor", "docenten", "wie zijn de"],
    "sv": ["professor", "lärare", "vilka är"],
    "tr": ["profesör", "öğretim üyeleri", "kimler"],
    "zh": ["教授", "教职员", "有哪些"],
    "tl": ["propesor", "faculty", "sino ang mga"],
    "hi": ["प्रोफेसर", "फैकल्टी", "कौन हैं"],
    "ta": ["பேராசிரியர்", "ஆசிரியர்கள்", "யார் யார்"],
    "ko": ["교수", "교직원", "누가 있"],
    "ja": ["教授", "教員", "誰がいる"],
    "ar": ["أستاذ", "هيئة التدريس", "من هم"],
    "he": ["פרופסור", "סגל", "מי הם"],
}

# ── Faculty reviews / ratings  →  faculty_reviews ──
RATING_WORDS = {
    "en": ["students say", "reviews", "rating", "good professor",
           "what do students", "how is the", "any good", "worth taking",
           "is he good", "is she good"],
    "es": ["estudiantes dicen", "reseñas", "calificación", "buen profesor",
           "qué dicen los estudiantes", "cómo es el"],
    "pt": ["alunos dizem", "avaliações", "classificação", "bom professor",
           "o que os alunos dizem", "como é o"],
    "fr": ["étudiants disent", "avis", "note", "bon professeur",
           "que disent les étudiants", "comment est le"],
    "de": ["studenten sagen", "bewertungen", "bewertung", "guter professor",
           "was sagen die studenten", "wie ist der"],
    "it": ["studenti dicono", "recensioni", "valutazione", "buon professore",
           "cosa dicono gli studenti", "com'è il"],
    "ru": ["студенты говорят", "отзывы", "рейтинг", "хороший преподаватель",
           "что говорят студенты", "какой преподаватель"],
    "uk": ["студенти кажуть", "відгуки", "рейтинг", "хороший викладач",
           "що кажуть студенти", "який викладач"],
    "pl": ["studenci mówią", "opinie", "ocena", "dobry profesor",
           "co mówią studenci", "jaki jest"],
    "el": ["φοιτητές λένε", "κριτικές", "βαθμολογία", "καλός καθηγητής",
           "τι λένε οι φοιτητές", "πώς είναι ο"],
    "nl": ["studenten zeggen", "beoordelingen", "waardering", "goede professor",
           "wat zeggen studenten", "hoe is de"],
    "sv": ["studenter säger", "recensioner", "betyg", "bra professor",
           "vad säger studenterna", "hur är"],
    "tr": ["öğrenciler diyor", "yorumlar", "değerlendirme", "iyi profesör",
           "öğrenciler ne diyor", "nasıl bir"],
    "zh": ["学生说", "评价", "评分", "好教授",
           "学生怎么说", "怎么样"],
    "tl": ["sabi ng mga estudyante", "reviews", "rating", "magaling na propesor",
           "ano sabi ng mga estudyante", "kumusta ang"],
    "hi": ["छात्र कहते हैं", "समीक्षाएं", "रेटिंग", "अच्छा प्रोफेसर",
           "छात्र क्या कहते हैं", "कैसा है"],
    "ta": ["மாணவர்கள் சொல்கிறார்கள்", "விமர்சனங்கள்", "மதிப்பீடு",
           "நல்ல பேராசிரியர்", "மாணவர்கள் என்ன சொல்கிறார்கள்", "எப்படி இருக்கிறார்"],
    "ko": ["학생들이 말하", "후기", "평점", "좋은 교수",
           "학생들은 어떻게", "어떤가요"],
    "ja": ["学生は言う", "評価", "評点", "いい教授",
           "学生はどう", "どうですか"],
    "ar": ["الطلاب يقولون", "تقييمات", "تقييم", "أستاذ جيد",
           "ماذا يقول الطلاب", "كيف هو"],
    "he": ["סטודנטים אומרים", "ביקורות", "דירוג", "מרצה טוב",
           "מה הסטודנטים אומרים", "איך ה"],
}

# ── Clubs / organizations  →  club ──
CLUB_WORDS = {
    "en": ["club", "organization", "society"],
    "es": ["club", "organización", "sociedad"],
    "pt": ["clube", "organização", "sociedade"],
    "fr": ["club", "organisation", "société"],
    "de": ["verein", "organisation", "gesellschaft"],
    "it": ["club", "organizzazione", "società"],
    "ru": ["клуб", "организация", "общество"],
    "uk": ["клуб", "організація", "товариство"],
    "pl": ["klub", "organizacja", "towarzystwo"],
    "el": ["σύλλογος", "οργάνωση", "κοινότητα"],
    "nl": ["club", "organisatie", "vereniging"],
    "sv": ["klubb", "organisation", "förening"],
    "tr": ["kulüp", "organizasyon", "topluluk"],
    "zh": ["俱乐部", "组织", "社团"],
    "tl": ["club", "organisasyon", "samahan"],
    "hi": ["क्लब", "संगठन", "सोसायटी"],
    "ta": ["கழகம்", "அமைப்பு", "சங்கம்"],
    "ko": ["동아리", "조직", "학회"],
    "ja": ["クラブ", "組織", "サークル"],
    "ar": ["نادي", "منظمة", "جمعية"],
    "he": ["מועדון", "ארגון", "אגודה"],
    # Named FGCU engineering orgs (proper nouns / acronyms — identical in every
    # language, so listing them once covers all languages). The "…Society" names
    # already match the generic "society"/"club" words above; Women in STEM,
    # IEEE, and the distinctive acronyms need their own entries. (Ambiguous short
    # acronyms like SWE/ASCE/FES are intentionally omitted — they collide with
    # ordinary words such as "sweden"/"ascend"/"fest".)
    "names": ["women in stem", "ieee", "nsbe", "bmes",
              "society of women engineers", "national society of black engineers",
              "biomedical engineering society", "american society of civil engineers",
              "florida engineering society", "software engineering club"],
}

# ── Institutes  →  general ──
# NOTE: "dendritic" and "eaglecybernest" are proper nouns; they are the same
# in every language and only need to appear once (kept under "en").
INSTITUTE_WORDS = {
    "en": ["institute", "dendritic", "eaglecybernest"],
    "es": ["instituto"],
    "pt": ["instituto"],
    "fr": ["institut"],
    "de": ["institut"],
    "it": ["istituto"],
    "ru": ["институт"],
    "uk": ["інститут"],
    "pl": ["instytut"],
    "el": ["ινστιτούτο"],
    "nl": ["instituut"],
    "sv": ["institut"],
    "tr": ["enstitü"],
    "zh": ["研究所"],
    "tl": ["instituto"],
    "hi": ["संस्थान"],
    "ta": ["நிறுவனம்"],
    "ko": ["연구소"],
    "ja": ["研究所"],
    "ar": ["معهد"],
    "he": ["מכון"],
}

# ── General (admissions, advising, research)  →  general + degree_map + research ──
GENERAL_WORDS = {
    "en": ["apply", "admission", "advisor", "advising", "research"],
    "es": ["aplicar", "admisión", "asesor", "asesoramiento", "investigación"],
    "pt": ["candidatar", "admissão", "orientador", "orientação", "pesquisa"],
    "fr": ["postuler", "admission", "conseiller", "orientation", "recherche"],
    "de": ["bewerben", "zulassung", "berater", "beratung", "forschung"],
    "it": ["candidarsi", "ammissione", "consulente", "consulenza", "ricerca"],
    "ru": ["поступить", "прием", "консультант", "консультирование", "исследование"],
    "uk": ["вступити", "вступ", "подати заявку", "консультант", "дослідження"],
    "pl": ["aplikować", "rekrutacja", "doradca", "doradztwo", "badania"],
    "el": ["αίτηση", "εισαγωγή", "σύμβουλος", "συμβουλευτική", "έρευνα"],
    "nl": ["aanmelden", "toelating", "adviseur", "advisering", "onderzoek"],
    "sv": ["ansöka", "antagning", "rådgivare", "rådgivning", "forskning"],
    "tr": ["başvuru", "kabul", "danışman", "danışmanlık", "araştırma"],
    "zh": ["申请", "录取", "顾问", "咨询", "研究"],
    "tl": ["mag-apply", "admission", "tagapayo", "pagpapayo", "pananaliksik"],
    "hi": ["आवेदन", "प्रवेश", "सलाहकार", "परामर्श", "अनुसंधान"],
    "ta": ["விண்ணப்பம்", "சேர்க்கை", "ஆலோசகர்", "ஆலோசனை", "ஆராய்ச்சி"],
    "ko": ["지원", "입학", "어드바이저", "상담", "연구"],
    "ja": ["出願", "入学", "アドバイザー", "相談", "研究"],
    "ar": ["تقديم", "قبول", "مرشد", "إرشاد", "بحث"],
    "he": ["להגיש", "קבלה", "יועץ", "ייעוץ", "מחקר"],
}


# ── Program detection  (program -> {lang: words}) ──────────
PROGRAM_WORDS = {
    "software_engineering": {
        "en": ["software engineering"], "es": ["ingeniería de software"],
        "pt": ["engenharia de software"], "fr": ["génie logiciel"],
        "de": ["softwaretechnik"], "it": ["ingegneria del software"],
        "ru": ["программная инженерия"], "uk": ["програмна інженерія"],
        "pl": ["inżynieria oprogramowania"], "el": ["μηχανική λογισμικού"],
        "nl": ["software-engineering"], "sv": ["mjukvaruteknik"],
        "tr": ["yazılım mühendisliği"], "zh": ["软件工程"],
        "tl": ["software engineering"], "hi": ["सॉफ्टवेयर इंजीनियरिंग"],
        "ta": ["மென்பொருள் பொறியியல்"], "ko": ["소프트웨어 공학"],
        "ja": ["ソフトウェア工学"], "ar": ["هندسة البرمجيات"],
        "he": ["הנדסת תוכנה"],
    },
    "computer_science": {
        "en": ["computer science", " cs ", "in cs"],
        "es": ["ciencias de la computación", "informática"],
        "pt": ["ciência da computação"], "fr": ["informatique"],
        "de": ["informatik"], "it": ["informatica"],
        "ru": ["информатика"], "uk": ["інформатика"],
        "pl": ["informatyka"], "el": ["επιστήμη υπολογιστών"],
        "nl": ["informatica"], "sv": ["datavetenskap"],
        "tr": ["bilgisayar bilimi"], "zh": ["计算机科学"],
        "tl": ["computer science"], "hi": ["कंप्यूटर विज्ञान"],
        "ta": ["கணினி அறிவியல்"], "ko": ["컴퓨터 과학"],
        "ja": ["コンピュータサイエンス"], "ar": ["علوم الحاسوب"],
        "he": ["מדעי המחשב"],
    },
    "civil_engineering": {
        "en": ["civil"], "es": ["civil"], "pt": ["civil"], "fr": ["civil"],
        "de": ["bauingenieur"], "it": ["civile"], "ru": ["гражданское"],
        "uk": ["цивільне"], "pl": ["lądowa"], "el": ["πολιτικός"],
        "nl": ["civiele"], "sv": ["bygg"], "tr": ["inşaat"],
        "zh": ["土木"], "tl": ["civil"], "hi": ["सिविल"],
        "ta": ["சிவில்"], "ko": ["토목"], "ja": ["土木"],
        "ar": ["مدني"], "he": ["אזרחית"],
    },
    "bioengineering": {
        "en": ["bioengineering", "biomedical"], "es": ["bioingeniería"],
        "pt": ["bioengenharia"], "fr": ["bio-ingénierie"],
        "de": ["bioingenieur"], "it": ["bioingegneria"],
        "ru": ["биоинженерия"], "uk": ["біоінженерія"],
        "pl": ["bioinżynieria"], "el": ["βιοϊατρική"],
        "nl": ["bio-engineering"], "sv": ["bioteknik"],
        "tr": ["biyomühendislik"], "zh": ["生物工程"],
        "tl": ["bioengineering"], "hi": ["जैव अभियांत्रिकी"],
        "ta": ["உயிர் பொறியியல்"], "ko": ["생명공학"],
        "ja": ["生体工学"], "ar": ["الهندسة الحيوية"],
        "he": ["ביו-הנדסה"],
    },
    "construction_management": {
        "en": ["construction"], "es": ["construcción"],
        "pt": ["construção"], "fr": ["construction"],
        "de": ["baumanagement"], "it": ["costruzioni"],
        "ru": ["строительство"], "uk": ["будівництво"],
        "pl": ["budownictwo"], "el": ["κατασκευές"],
        "nl": ["bouw"], "sv": ["byggledning"], "tr": ["inşaat yönetimi"],
        "zh": ["建筑管理"], "tl": ["construction"],
        "hi": ["निर्माण"], "ta": ["கட்டுமானம்"],
        "ko": ["건설"], "ja": ["建設"], "ar": ["إدارة البناء"],
        "he": ["בנייה"],
    },
    "environmental_engineering": {
        "en": ["environmental"], "es": ["ambiental"],
        "pt": ["ambiental"], "fr": ["environnement"],
        "de": ["umwelt"], "it": ["ambientale"],
        "ru": ["экологическая"], "uk": ["екологічна"],
        "pl": ["środowiska"], "el": ["περιβαλλοντικός"],
        "nl": ["milieu"], "sv": ["miljö"], "tr": ["çevre"],
        "zh": ["环境"], "tl": ["environmental"],
        "hi": ["पर्यावरण"], "ta": ["சுற்றுச்சூழல்"],
        "ko": ["환경"], "ja": ["環境"], "ar": ["بيئي"],
        "he": ["סביבתית"],
    },
}


# ── Term / season detection  (season -> {lang: words}) ─────
SEASON_WORDS = {
    "fall": {
        "en": ["fall"], "es": ["otoño"], "pt": ["outono"], "fr": ["automne"],
        "de": ["herbst"], "it": ["autunno"], "ru": ["осень"], "uk": ["осінь"],
        "pl": ["jesień"], "el": ["φθινόπωρο"], "nl": ["herfst"],
        "sv": ["höst"], "tr": ["sonbahar", "güz"], "zh": ["秋季", "秋天"],
        "tl": ["taglagas"], "hi": ["पतझड़"], "ta": ["இலையுதிர்"],
        "ko": ["가을"], "ja": ["秋"], "ar": ["خريف"], "he": ["סתיו"],
    },
    "spring": {
        "en": ["spring"], "es": ["primavera"], "pt": ["primavera"],
        "fr": ["printemps"], "de": ["frühling"], "it": ["primavera"],
        "ru": ["весна"], "uk": ["весна"], "pl": ["wiosna"],
        "el": ["άνοιξη"], "nl": ["lente"], "sv": ["vår"],
        "tr": ["ilkbahar", "bahar"], "zh": ["春季", "春天"],
        "tl": ["tagsibol"], "hi": ["वसंत"], "ta": ["வசந்தம்"],
        "ko": ["봄"], "ja": ["春"], "ar": ["ربيع"], "he": ["אביב"],
    },
    "summer": {
        "en": ["summer"], "es": ["verano"], "pt": ["verão"],
        "fr": ["été", "ete"], "de": ["sommer"], "it": ["estate"],
        "ru": ["лето"], "uk": ["літо"], "pl": ["lato"],
        "el": ["καλοκαίρι"], "nl": ["zomer"], "sv": ["sommar"],
        "tr": ["yaz"], "zh": ["夏季", "夏天"], "tl": ["tag-init"],
        "hi": ["गर्मी"], "ta": ["கோடை"], "ko": ["여름"],
        "ja": ["夏"], "ar": ["صيف"], "he": ["קיץ"],
    },
}


# ── Page-data topics ───────────────────────────────────────
# Cover the data/pages/* sections (admissions, student life, campus info,
# policies, departments, programs) that used to all collapse into one generic
# bucket. English-led since the source pages are English; the unfiltered
# fallback still catches non-English questions, and these can be extended per
# language later.
ADMISSIONS_WORDS = {
    "en": ["apply", "application", "admission", "admissions", "enroll", "enrollment",
           "how do i get in", "get accepted", "admission requirement", "transfer student",
           "international student", "deadline to apply", "freshman", "non-degree"],
    "es": ["cómo me inscribo", "admisión", "inscripción", "solicitud de admisión"],
    "fr": ["admission", "candidature", "comment s'inscrire"],
}
STUDENT_LIFE_WORDS = {
    "en": ["student life", "student org", "student organization", "get involved",
           "involvement", "student event", "campus event", "recreation", "wellness",
           "dean of students", "holmes is your home", "hard hat ceremony", "traditions",
           "club fair", "things to do", "student government", "trio",
           "eaglehacks", "hackathon", "e-week", "e week", "eagle game jam", "game jam",
           "capture the flag", "ctf night", "game night", "pc building workshop",
           "speaker night", "study event", "summer camp", "internship", "community event"],
    "es": ["vida estudiantil", "organización estudiantil"],
}
POLICY_WORDS = {
    "en": ["policy", "policies", "ethics", "compliance", "code of conduct",
           "academic integrity", "state authorization", "government relations",
           "title ix", "student conduct"],
}
CAMPUS_WORDS = {
    "en": ["holmes", "holmes hall", "what building", "which building", "where is",
           "where can i find", "located", "location of", "address", "directions",
           "about fgcu", "about the college", "about the school", "whitaker", "wce",
           "campus map", "what is fgcu", "office of"],
    "es": ["dónde está", "ubicación", "qué edificio"],
}
DEPARTMENT_WORDS = {
    "en": ["department", "departments", "school of", "which department",
           "what departments", "computing and software engineering"],
}
PROGRAM_TOPIC_WORDS = {
    "en": ["program", "programs", "concentration", "graduate program", "phd",
           "doctoral", "what can i study", "graduate studies", "internship",
           "internships", "academics", "what programs", "bachelor of", "master of"],
    "es": ["programa", "concentración"],
}


# ── Helpers ────────────────────────────────────────────────
def flatten(group: dict) -> list:
    """Combine all languages of a category dict into one flat list."""
    words = []
    for lang_words in group.values():
        words.extend(lang_words)
    return words


# Pre-flattened lists the router uses directly.
ALL_SCHEDULE     = flatten(SCHEDULE_WORDS)
ALL_DESCRIPTION  = flatten(DESCRIPTION_WORDS)
ALL_HELP         = flatten(HELP_WORDS)
ALL_CURRICULUM   = flatten(CURRICULUM_WORDS)
ALL_FACULTY      = flatten(FACULTY_WORDS)
ALL_RATING       = flatten(RATING_WORDS)
ALL_CLUB         = flatten(CLUB_WORDS)
ALL_INSTITUTE    = flatten(INSTITUTE_WORDS)
ALL_GENERAL      = flatten(GENERAL_WORDS)
ALL_HUB_OVERRIDE = flatten(LEARNING_HUB_OVERRIDE)
ALL_ADMISSIONS   = flatten(ADMISSIONS_WORDS)
ALL_STUDENT_LIFE = flatten(STUDENT_LIFE_WORDS)
ALL_POLICY       = flatten(POLICY_WORDS)
ALL_CAMPUS       = flatten(CAMPUS_WORDS)
ALL_DEPARTMENT   = flatten(DEPARTMENT_WORDS)
ALL_PROGRAM      = flatten(PROGRAM_TOPIC_WORDS)

SUPPORTED_LANGUAGES = [
    "English", "Spanish", "Portuguese", "French", "German", "Italian",
    "Russian", "Ukrainian", "Polish", "Greek", "Dutch", "Swedish", "Turkish",
    "Chinese", "Tagalog", "Hindi", "Tamil", "Korean", "Japanese", "Arabic",
    "Hebrew",
]