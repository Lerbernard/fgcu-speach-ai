"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";

// Point this at your backend. Local dev = localhost:8080.
const API_BASE = "http://localhost:8080";

type Phase = "idle" | "arming" | "recording" | "transcribing" | "thinking" | "speaking";

// Languages the assistant supports: English name (sent to backend) + native label.
const LANGUAGES: { name: string; native: string }[] = [
  { name: "English", native: "English" },
  { name: "Spanish", native: "Español" },
  { name: "Portuguese", native: "Português" },
  { name: "French", native: "Français" },
  { name: "German", native: "Deutsch" },
  { name: "Italian", native: "Italiano" },
  { name: "Russian", native: "Русский" },
  { name: "Ukrainian", native: "Українська" },
  { name: "Polish", native: "Polski" },
  { name: "Greek", native: "Ελληνικά" },
  { name: "Dutch", native: "Nederlands" },
  { name: "Swedish", native: "Svenska" },
  { name: "Turkish", native: "Türkçe" },
  { name: "Chinese", native: "中文" },
  { name: "Tagalog", native: "Tagalog" },
  { name: "Hindi", native: "हिन्दी" },
  { name: "Tamil", native: "தமிழ்" },
  { name: "Korean", native: "한국어" },
  { name: "Japanese", native: "日本語" },
  { name: "Arabic", native: "العربية" },
  { name: "Hebrew", native: "עברית" },
];

// UI text in every supported language. The whole interface switches to the
// active language (selected, or detected from the last question).
type UIStrings = {
  eyebrow: string;
  title1: string;
  titleAccent: string;
  sub: string;
  autoLabel: string;
  speakIn: string;
  tapToAsk: string;
  getReady: string;
  speakNow: string;
  reading: string;
  thinking: string;
  speaking: string;
  youAsked: string;
  eagle: string;
  replay: string;
  voiceUnavailable: string;
  micError: string;
  noCatch: string;
  backendError: string;
  voiceTab: string;
  textTab: string;
  typePlaceholder: string;
  send: string;
  newChat: string;
  home: string;
};

const UI: Record<string, UIStrings> = {
  English: { eyebrow: "U.A. Whitaker College of Engineering", title1: "Ask the ", titleAccent: "Eagle", sub: "Your voice assistant for courses, faculty, advising, and campus life, in your language.", autoLabel: "Detect language automatically", speakIn: "I'll speak in", tapToAsk: "Tap to ask", getReady: "Get ready", speakNow: "Speak now, tap again to send", reading: "Reading your question", thinking: "Finding the answer", speaking: "Speaking", youAsked: "You asked", eagle: "Eagle", replay: "replay", voiceUnavailable: "Voice playback is unavailable right now, but here's the answer above.", micError: "Couldn't reach your microphone. Check that your browser has mic permission.", noCatch: "I didn't catch that. Try again and speak a little closer to the mic.", backendError: "Something went wrong reaching the assistant. Is the backend running?", voiceTab: "Voice", textTab: "Text", typePlaceholder: "Type your question", send: "Send", newChat: "New chat", home: "Home" },
  Spanish: { eyebrow: "Facultad de Ingeniería U.A. Whitaker", title1: "Pregúntale al ", titleAccent: "Águila", sub: "Tu asistente de voz para cursos, profesores, asesoría y vida universitaria, en tu idioma.", autoLabel: "Detectar idioma automáticamente", speakIn: "Hablaré en", tapToAsk: "Toca para preguntar", getReady: "Prepárate", speakNow: "Habla ahora, toca de nuevo para enviar", reading: "Leyendo tu pregunta", thinking: "Buscando la respuesta", speaking: "Hablando", youAsked: "Preguntaste", eagle: "Águila", replay: "repetir", voiceUnavailable: "La reproducción de voz no está disponible ahora, pero aquí está la respuesta.", micError: "No se pudo acceder al micrófono. Verifica los permisos del navegador.", noCatch: "No te entendí. Inténtalo de nuevo y habla más cerca del micrófono.", backendError: "Algo salió mal al contactar al asistente. ¿Está funcionando el servidor?", voiceTab: "Voz", textTab: "Texto", typePlaceholder: "Escribe tu pregunta", send: "Enviar", newChat: "Nuevo chat", home: "Inicio" },
  Portuguese: { eyebrow: "Faculdade de Engenharia U.A. Whitaker", title1: "Pergunte à ", titleAccent: "Águia", sub: "Seu assistente de voz para cursos, professores, orientação e vida no campus, no seu idioma.", autoLabel: "Detectar idioma automaticamente", speakIn: "Vou falar em", tapToAsk: "Toque para perguntar", getReady: "Prepare-se", speakNow: "Fale agora, toque novamente para enviar", reading: "Lendo sua pergunta", thinking: "Procurando a resposta", speaking: "Falando", youAsked: "Você perguntou", eagle: "Águia", replay: "repetir", voiceUnavailable: "A reprodução de voz não está disponível agora, mas aqui está a resposta acima.", micError: "Não foi possível acessar o microfone. Verifique as permissões do navegador.", noCatch: "Não entendi. Tente novamente e fale mais perto do microfone.", backendError: "Algo deu errado ao contatar o assistente. O servidor está rodando?", voiceTab: "Voz", textTab: "Texto", typePlaceholder: "Digite sua pergunta", send: "Enviar", newChat: "Nova conversa", home: "Início" },
  French: { eyebrow: "Faculté d'Ingénierie U.A. Whitaker", title1: "Demandez à l'", titleAccent: "Aigle", sub: "Votre assistant vocal pour les cours, les professeurs, l'orientation et la vie sur le campus, dans votre langue.", autoLabel: "Détecter la langue automatiquement", speakIn: "Je parlerai en", tapToAsk: "Touchez pour demander", getReady: "Préparez-vous", speakNow: "Parlez maintenant, touchez à nouveau pour envoyer", reading: "Lecture de votre question", thinking: "Recherche de la réponse", speaking: "En train de parler", youAsked: "Vous avez demandé", eagle: "Aigle", replay: "rejouer", voiceUnavailable: "La lecture vocale n'est pas disponible pour le moment, mais voici la réponse ci-dessus.", micError: "Impossible d'accéder au microphone. Vérifiez les autorisations du navigateur.", noCatch: "Je n'ai pas compris. Réessayez en parlant plus près du micro.", backendError: "Un problème est survenu avec l'assistant. Le serveur est-il en marche ?", voiceTab: "Voix", textTab: "Texte", typePlaceholder: "Tapez votre question", send: "Envoyer", newChat: "Nouvelle conversation", home: "Accueil" },
  German: { eyebrow: "U.A. Whitaker College of Engineering", title1: "Frag den ", titleAccent: "Adler", sub: "Dein Sprachassistent für Kurse, Dozenten, Beratung und Campusleben, in deiner Sprache.", autoLabel: "Sprache automatisch erkennen", speakIn: "Ich spreche in", tapToAsk: "Zum Fragen tippen", getReady: "Mach dich bereit", speakNow: "Sprich jetzt, tippe erneut zum Senden", reading: "Deine Frage wird gelesen", thinking: "Antwort wird gesucht", speaking: "Spricht", youAsked: "Du hast gefragt", eagle: "Adler", replay: "wiederholen", voiceUnavailable: "Sprachwiedergabe ist gerade nicht verfügbar, aber hier ist die Antwort oben.", micError: "Mikrofon nicht erreichbar. Prüfe die Mikrofonberechtigung des Browsers.", noCatch: "Das habe ich nicht verstanden. Versuche es näher am Mikrofon erneut.", backendError: "Beim Erreichen des Assistenten ist etwas schiefgelaufen. Läuft der Server?", voiceTab: "Stimme", textTab: "Text", typePlaceholder: "Gib deine Frage ein", send: "Senden", newChat: "Neuer Chat", home: "Startseite" },
  Italian: { eyebrow: "Facoltà di Ingegneria U.A. Whitaker", title1: "Chiedi all'", titleAccent: "Aquila", sub: "Il tuo assistente vocale per corsi, docenti, orientamento e vita del campus, nella tua lingua.", autoLabel: "Rileva lingua automaticamente", speakIn: "Parlerò in", tapToAsk: "Tocca per chiedere", getReady: "Preparati", speakNow: "Parla ora, tocca di nuovo per inviare", reading: "Lettura della tua domanda", thinking: "Ricerca della risposta", speaking: "Sto parlando", youAsked: "Hai chiesto", eagle: "Aquila", replay: "riascolta", voiceUnavailable: "La riproduzione vocale non è disponibile ora, ma ecco la risposta sopra.", micError: "Impossibile accedere al microfono. Controlla i permessi del browser.", noCatch: "Non ho capito. Riprova parlando più vicino al microfono.", backendError: "Qualcosa è andato storto con l'assistente. Il server è in funzione?", voiceTab: "Voce", textTab: "Testo", typePlaceholder: "Scrivi la tua domanda", send: "Invia", newChat: "Nuova chat", home: "Home" },
  Russian: { eyebrow: "Инженерный колледж U.A. Whitaker", title1: "Спроси ", titleAccent: "Орла", sub: "Ваш голосовой помощник по курсам, преподавателям, консультациям и студенческой жизни, на вашем языке.", autoLabel: "Определять язык автоматически", speakIn: "Я буду говорить на", tapToAsk: "Нажмите, чтобы спросить", getReady: "Приготовьтесь", speakNow: "Говорите, нажмите снова для отправки", reading: "Читаю ваш вопрос", thinking: "Ищу ответ", speaking: "Говорю", youAsked: "Вы спросили", eagle: "Орёл", replay: "повтор", voiceUnavailable: "Воспроизведение голоса сейчас недоступно, но ответ выше.", micError: "Не удалось получить доступ к микрофону. Проверьте разрешения браузера.", noCatch: "Я не расслышал. Попробуйте снова, ближе к микрофону.", backendError: "Что-то пошло не так при обращении к помощнику. Сервер запущен?", voiceTab: "Голос", textTab: "Текст", typePlaceholder: "Введите ваш вопрос", send: "Отправить", newChat: "Новый чат", home: "Главная" },
  Ukrainian: { eyebrow: "Інженерний коледж U.A. Whitaker", title1: "Запитай ", titleAccent: "Орла", sub: "Ваш голосовий помічник з курсів, викладачів, консультацій та студентського життя, вашою мовою.", autoLabel: "Визначати мову автоматично", speakIn: "Я говоритиму", tapToAsk: "Натисніть, щоб запитати", getReady: "Приготуйтеся", speakNow: "Говоріть, натисніть знову для надсилання", reading: "Читаю ваше запитання", thinking: "Шукаю відповідь", speaking: "Говорю", youAsked: "Ви запитали", eagle: "Орел", replay: "повтор", voiceUnavailable: "Відтворення голосу зараз недоступне, але відповідь вище.", micError: "Не вдалося отримати доступ до мікрофона. Перевірте дозволи браузера.", noCatch: "Я не розчув. Спробуйте ще раз, ближче до мікрофона.", backendError: "Щось пішло не так під час звернення до помічника. Сервер працює?", voiceTab: "Голос", textTab: "Текст", typePlaceholder: "Введіть ваше запитання", send: "Надіслати", newChat: "Новий чат", home: "Головна" },
  Polish: { eyebrow: "Wydział Inżynierii U.A. Whitaker", title1: "Zapytaj ", titleAccent: "Orła", sub: "Twój asystent głosowy do kursów, wykładowców, doradztwa i życia studenckiego, w twoim języku.", autoLabel: "Wykrywaj język automatycznie", speakIn: "Będę mówić po", tapToAsk: "Dotknij, aby zapytać", getReady: "Przygotuj się", speakNow: "Mów teraz, dotknij ponownie, aby wysłać", reading: "Czytam twoje pytanie", thinking: "Szukam odpowiedzi", speaking: "Mówię", youAsked: "Zapytałeś", eagle: "Orzeł", replay: "powtórz", voiceUnavailable: "Odtwarzanie głosu jest teraz niedostępne, ale odpowiedź jest powyżej.", micError: "Nie można uzyskać dostępu do mikrofonu. Sprawdź uprawnienia przeglądarki.", noCatch: "Nie zrozumiałem. Spróbuj ponownie, mówiąc bliżej mikrofonu.", backendError: "Coś poszło nie tak z asystentem. Czy serwer działa?", voiceTab: "Głos", textTab: "Tekst", typePlaceholder: "Wpisz swoje pytanie", send: "Wyślij", newChat: "Nowy czat", home: "Strona główna" },
  Greek: { eyebrow: "Πολυτεχνική Σχολή U.A. Whitaker", title1: "Ρώτησε τον ", titleAccent: "Αετό", sub: "Ο φωνητικός σου βοηθός για μαθήματα, καθηγητές, συμβουλευτική και ζωή στην πανεπιστημιούπολη, στη γλώσσα σου.", autoLabel: "Αυτόματη ανίχνευση γλώσσας", speakIn: "Θα μιλήσω στα", tapToAsk: "Πάτησε για ερώτηση", getReady: "Ετοιμάσου", speakNow: "Μίλα τώρα, πάτησε ξανά για αποστολή", reading: "Διαβάζω την ερώτησή σου", thinking: "Ψάχνω την απάντηση", speaking: "Μιλάω", youAsked: "Ρώτησες", eagle: "Αετός", replay: "επανάληψη", voiceUnavailable: "Η φωνητική αναπαραγωγή δεν είναι διαθέσιμη τώρα, αλλά η απάντηση είναι παραπάνω.", micError: "Δεν ήταν δυνατή η πρόσβαση στο μικρόφωνο. Έλεγξε τα δικαιώματα του προγράμματος περιήγησης.", noCatch: "Δεν κατάλαβα. Δοκίμασε ξανά πιο κοντά στο μικρόφωνο.", backendError: "Κάτι πήγε στραβά με τον βοηθό. Λειτουργεί ο διακομιστής;", voiceTab: "Φωνή", textTab: "Κείμενο", typePlaceholder: "Πληκτρολόγησε την ερώτησή σου", send: "Αποστολή", newChat: "Νέα συνομιλία", home: "Αρχική" },
  Dutch: { eyebrow: "U.A. Whitaker Faculteit Techniek", title1: "Vraag de Adelaar", titleAccent: "", sub: "Je spraakassistent voor cursussen, docenten, advies en campusleven, in jouw taal.", autoLabel: "Taal automatisch detecteren", speakIn: "Ik spreek in het", tapToAsk: "Tik om te vragen", getReady: "Maak je klaar", speakNow: "Spreek nu, tik nogmaals om te verzenden", reading: "Je vraag wordt gelezen", thinking: "De antwoord zoeken", speaking: "Aan het spreken", youAsked: "Je vroeg", eagle: "Adelaar", replay: "opnieuw", voiceUnavailable: "Spraakweergave is nu niet beschikbaar, maar hier is het antwoord hierboven.", micError: "Kan de microfoon niet bereiken. Controleer de microfoontoestemming van de browser.", noCatch: "Ik verstond het niet. Probeer het opnieuw dichter bij de microfoon.", backendError: "Er ging iets mis met de assistent. Draait de server?", voiceTab: "Stem", textTab: "Tekst", typePlaceholder: "Typ je vraag", send: "Versturen", newChat: "Nieuwe chat", home: "Home" },
  Swedish: { eyebrow: "U.A. Whitaker Ingenjörshögskola", title1: "Fråga ", titleAccent: "Örnen", sub: "Din röstassistent för kurser, lärare, rådgivning och campusliv, på ditt språk.", autoLabel: "Identifiera språk automatiskt", speakIn: "Jag talar på", tapToAsk: "Tryck för att fråga", getReady: "Gör dig redo", speakNow: "Tala nu, tryck igen för att skicka", reading: "Läser din fråga", thinking: "Söker svaret", speaking: "Talar", youAsked: "Du frågade", eagle: "Örn", replay: "spela upp", voiceUnavailable: "Röståtergivning är inte tillgänglig just nu, men här är svaret ovan.", micError: "Kunde inte nå mikrofonen. Kontrollera webbläsarens mikrofonbehörighet.", noCatch: "Jag uppfattade inte det. Försök igen närmare mikrofonen.", backendError: "Något gick fel med assistenten. Körs servern?", voiceTab: "Röst", textTab: "Text", typePlaceholder: "Skriv din fråga", send: "Skicka", newChat: "Ny chatt", home: "Hem" },
  Turkish: { eyebrow: "U.A. Whitaker Mühendislik Fakültesi", title1: "Kartal'a Sor", titleAccent: "", sub: "Dersler, öğretim üyeleri, danışmanlık ve kampüs yaşamı için sesli asistanınız, kendi dilinizde.", autoLabel: "Dili otomatik algıla", speakIn: "Şu dilde konuşacağım:", tapToAsk: "Sormak için dokun", getReady: "Hazır ol", speakNow: "Şimdi konuş, göndermek için tekrar dokun", reading: "Sorunuz okunuyor", thinking: "Cevap aranıyor", speaking: "Konuşuyor", youAsked: "Sordunuz", eagle: "Kartal", replay: "tekrar", voiceUnavailable: "Sesli oynatma şu anda kullanılamıyor, ancak cevap yukarıda.", micError: "Mikrofona erişilemedi. Tarayıcı mikrofon iznini kontrol edin.", noCatch: "Anlayamadım. Mikrofona daha yakın konuşarak tekrar deneyin.", backendError: "Asistana ulaşırken bir sorun oluştu. Sunucu çalışıyor mu?", voiceTab: "Ses", textTab: "Metin", typePlaceholder: "Sorunuzu yazın", send: "Gönder", newChat: "Yeni sohbet", home: "Ana sayfa" },
  Chinese: { eyebrow: "U.A. Whitaker 工程学院", title1: "询问", titleAccent: "雄鹰", sub: "您的语音助手，用您的语言提供课程、教师、咨询和校园生活信息。", autoLabel: "自动检测语言", speakIn: "我将使用", tapToAsk: "点击提问", getReady: "准备好", speakNow: "现在说话，再次点击发送", reading: "正在读取您的问题", thinking: "正在寻找答案", speaking: "正在说话", youAsked: "您问", eagle: "雄鹰", replay: "重播", voiceUnavailable: "目前无法进行语音播放，但答案在上方。", micError: "无法访问麦克风。请检查浏览器的麦克风权限。", noCatch: "我没听清。请靠近麦克风再试一次。", backendError: "联系助手时出错。服务器在运行吗？", voiceTab: "语音", textTab: "文字", typePlaceholder: "输入您的问题", send: "发送", newChat: "新对话", home: "主页" },
  Tagalog: { eyebrow: "U.A. Whitaker College of Engineering", title1: "Tanungin ang ", titleAccent: "Agila", sub: "Ang iyong voice assistant para sa mga kurso, guro, payo, at buhay sa campus, sa iyong wika.", autoLabel: "Awtomatikong tukuyin ang wika", speakIn: "Magsasalita ako sa", tapToAsk: "I-tap para magtanong", getReady: "Maghanda", speakNow: "Magsalita na, i-tap ulit para ipadala", reading: "Binabasa ang iyong tanong", thinking: "Hinahanap ang sagot", speaking: "Nagsasalita", youAsked: "Tinanong mo", eagle: "Agila", replay: "ulitin", voiceUnavailable: "Hindi available ang voice playback ngayon, pero nasa itaas ang sagot.", micError: "Hindi maabot ang mikropono. Tingnan ang pahintulot ng browser.", noCatch: "Hindi kita narinig. Subukan ulit nang mas malapit sa mikropono.", backendError: "May mali sa pag-abot sa assistant. Gumagana ba ang server?", voiceTab: "Boses", textTab: "Teksto", typePlaceholder: "I-type ang iyong tanong", send: "Ipadala", newChat: "Bagong chat", home: "Home" },
  Hindi: { eyebrow: "U.A. Whitaker इंजीनियरिंग कॉलेज", title1: "ईगल से पूछें", titleAccent: "", sub: "पाठ्यक्रमों, शिक्षकों, सलाह और कैंपस जीवन के लिए आपका वॉयस असिस्टेंट, आपकी भाषा में।", autoLabel: "भाषा स्वचालित रूप से पहचानें", speakIn: "मैं बोलूंगा", tapToAsk: "पूछने के लिए टैप करें", getReady: "तैयार हो जाइए", speakNow: "अब बोलें, भेजने के लिए फिर से टैप करें", reading: "आपका प्रश्न पढ़ रहे हैं", thinking: "उत्तर खोज रहे हैं", speaking: "बोल रहे हैं", youAsked: "आपने पूछा", eagle: "ईगल", replay: "फिर से चलाएं", voiceUnavailable: "वॉयस प्लेबैक अभी उपलब्ध नहीं है, लेकिन उत्तर ऊपर है।", micError: "माइक्रोफ़ोन तक नहीं पहुंच सके। ब्राउज़र की माइक अनुमति जांचें।", noCatch: "मैं समझ नहीं पाया। माइक के पास बोलकर फिर से कोशिश करें।", backendError: "असिस्टेंट तक पहुंचने में कुछ गलत हुआ। क्या सर्वर चल रहा है?", voiceTab: "आवाज़", textTab: "टेक्स्ट", typePlaceholder: "अपना प्रश्न लिखें", send: "भेजें", newChat: "नई चैट", home: "होम" },
  Tamil: { eyebrow: "U.A. Whitaker பொறியியல் கல்லூரி", title1: "கழுகிடம் கேள்", titleAccent: "", sub: "படிப்புகள், ஆசிரியர்கள், ஆலோசனை மற்றும் வளாக வாழ்க்கைக்கான உங்கள் குரல் உதவியாளர், உங்கள் மொழியில்.", autoLabel: "மொழியைத் தானாகக் கண்டறி", speakIn: "நான் பேசுவேன்", tapToAsk: "கேட்க தட்டவும்", getReady: "தயாராகுங்கள்", speakNow: "இப்போது பேசுங்கள், அனுப்ப மீண்டும் தட்டவும்", reading: "உங்கள் கேள்வியைப் படிக்கிறது", thinking: "பதிலைத் தேடுகிறது", speaking: "பேசுகிறது", youAsked: "நீங்கள் கேட்டீர்கள்", eagle: "கழுகு", replay: "மீண்டும்", voiceUnavailable: "குரல் இப்போது கிடைக்கவில்லை, ஆனால் பதில் மேலே உள்ளது.", micError: "மைக்ரோஃபோனை அணுக முடியவில்லை. உலாவியின் அனुமதியைச் சரிபார்க்கவும்.", noCatch: "எனக்குப் புரியவில்லை. மைக்கிற்கு அருகில் மீண்டும் முயற்சிக்கவும்.", backendError: "உதவியாளரை அணுகுவதில் சிக்கல். சர்வர் இயங்குகிறதா?", voiceTab: "குரல்", textTab: "உரை", typePlaceholder: "உங்கள் கேள்வியைத் தட்டச்சு செய்யவும்", send: "அனுப்பு", newChat: "புதிய அரட்டை", home: "முகப்பு" },
  Korean: { eyebrow: "U.A. Whitaker 공과대학", title1: "이글에게 물어보세요", titleAccent: "", sub: "강좌, 교수진, 상담, 캠퍼스 생활을 위한 당신의 언어로 된 음성 도우미.", autoLabel: "언어 자동 감지", speakIn: "다음 언어로 말합니다:", tapToAsk: "탭하여 질문", getReady: "준비하세요", speakNow: "지금 말하세요, 보내려면 다시 탭하세요", reading: "질문을 읽는 중", thinking: "답을 찾는 중", speaking: "말하는 중", youAsked: "질문하셨습니다", eagle: "이글", replay: "다시 재생", voiceUnavailable: "지금은 음성 재생을 사용할 수 없지만 위에 답변이 있습니다.", micError: "마이크에 접근할 수 없습니다. 브라우저의 마이크 권한을 확인하세요.", noCatch: "잘 못 들었습니다. 마이크에 더 가까이서 다시 시도하세요.", backendError: "도우미 연결 중 문제가 발생했습니다. 서버가 실행 중입니까?", voiceTab: "음성", textTab: "텍스트", typePlaceholder: "질문을 입력하세요", send: "보내기", newChat: "새 대화", home: "홈" },
  Japanese: { eyebrow: "U.A. Whitaker 工学部", title1: "イーグルに聞いてみよう", titleAccent: "", sub: "コース、教員、アドバイス、キャンパスライフのための、あなたの言語の音声アシスタント。", autoLabel: "言語を自動検出", speakIn: "次の言語で話します:", tapToAsk: "タップして質問", getReady: "準備して", speakNow: "今話してください、もう一度タップで送信", reading: "質問を読んでいます", thinking: "答えを探しています", speaking: "話しています", youAsked: "あなたの質問", eagle: "イーグル", replay: "再生", voiceUnavailable: "現在音声再生は利用できませんが、上に回答があります。", micError: "マイクにアクセスできません。ブラウザのマイク許可を確認してください。", noCatch: "聞き取れませんでした。マイクに近づいてもう一度お試しください。", backendError: "アシスタントへの接続で問題が発生しました。サーバーは起動していますか？", voiceTab: "音声", textTab: "テキスト", typePlaceholder: "質問を入力してください", send: "送信", newChat: "新しいチャット", home: "ホーム" },
  Arabic: { eyebrow: "كلية الهندسة U.A. Whitaker", title1: "اسأل ", titleAccent: "النسر", sub: "مساعدك الصوتي للمقررات والأساتذة والإرشاد والحياة الجامعية، بلغتك.", autoLabel: "اكتشاف اللغة تلقائيًا", speakIn: "سأتحدث بـ", tapToAsk: "اضغط للسؤال", getReady: "استعد", speakNow: "تحدث الآن، اضغط مرة أخرى للإرسال", reading: "جارٍ قراءة سؤالك", thinking: "جارٍ البحث عن الإجابة", speaking: "يتحدث", youAsked: "لقد سألت", eagle: "النسر", replay: "إعادة", voiceUnavailable: "تشغيل الصوت غير متاح الآن، لكن الإجابة في الأعلى.", micError: "تعذر الوصول إلى الميكروفون. تحقق من أذونات المتصفح.", noCatch: "لم أسمع ذلك. حاول مرة أخرى بالقرب من الميكروفون.", backendError: "حدث خطأ أثناء الوصول إلى المساعد. هل الخادم يعمل؟", voiceTab: "صوت", textTab: "نص", typePlaceholder: "اكتب سؤالك", send: "إرسال", newChat: "محادثة جديدة", home: "الرئيسية" },
  Hebrew: { eyebrow: "הפקולטה להנדסה U.A. Whitaker", title1: "שאל את ", titleAccent: "הנשר", sub: "עוזר הקול שלך לקורסים, מרצים, ייעוץ וחיי קמפוס, בשפה שלך.", autoLabel: "זהה שפה אוטומטית", speakIn: "אדבר ב", tapToAsk: "הקש כדי לשאול", getReady: "התכונן", speakNow: "דבר עכשיו, הקש שוב לשליחה", reading: "קורא את השאלה שלך", thinking: "מחפש את התשובה", speaking: "מדבר", youAsked: "שאלת", eagle: "נשר", replay: "השמע שוב", voiceUnavailable: "השמעת הקול אינה זמינה כעת, אך התשובה למעלה.", micError: "לא ניתן לגשת למיקרופון. בדוק את הרשאות הדפדפן.", noCatch: "לא הבנתי. נסה שוב קרוב יותר למיקרופון.", backendError: "משהו השתבש בפנייה לעוזר. האם השרת פועל?", voiceTab: "קול", textTab: "טקסט", typePlaceholder: "הקלד את שאלתך", send: "שלח", newChat: "צ'אט חדש", home: "בית" },
};

// Map a backend-detected language name to our UI keys (handles the combined case).
function normalizeLang(name: string): string {
  if (!name) return "English";
  if (name.includes("Russian") || name.includes("Ukrainian")) return "Russian";
  return UI[name] ? name : "English";
}

const RTL = new Set(["Arabic", "Hebrew"]);

export default function Home() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [transcript, setTranscript] = useState("");
  const [answer, setAnswer] = useState("");
  const [messages, setMessages] = useState<{ question: string; answer: string }[]>([]);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState("");
  const [level, setLevel] = useState(0);
  const [mode, setMode] = useState<"voice" | "text">("voice");
  const [textInput, setTextInput] = useState("");
  const [isPaused, setIsPaused] = useState(false);              // is the audio paused?
  const [playingIdx, setPlayingIdx] = useState<number | null>(null); // which answer is playing

  const [autoDetect, setAutoDetect] = useState(true);
  const [selectedLang, setSelectedLang] = useState("English"); // used when auto is off
  const [detectedLang, setDetectedLang] = useState("English"); // set after a question, used when auto is on
  const [langOpen, setLangOpen] = useState(false);
  const langRef = useRef<HTMLDivElement | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);

  const busy = phase === "transcribing" || phase === "thinking" || phase === "speaking";
  // Active UI language is derived, not stored: when auto-detect is off the
  // user's selection drives it; when on, the last detected language does.
  const activeLang = autoDetect ? detectedLang : selectedLang;
  const t = UI[activeLang] || UI.English;
  const rtl = RTL.has(activeLang);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (audioCtxRef.current) audioCtxRef.current.close();
    };
  }, []);

  // Auto-scroll the thread to the newest message as the conversation grows.
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, transcript, phase]);

  useEffect(() => {
    if (!langOpen) return;
    function onClick(e: MouseEvent) {
      if (langRef.current && !langRef.current.contains(e.target as Node)) setLangOpen(false);
    }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setLangOpen(false); }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [langOpen]);

  async function startRecording() {
    setError("");
    setAnswer("");
    setTranscript("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      audioCtxRef.current = ctx;
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128;
          sum += v * v;
        }
        setLevel(Math.min(1, Math.sqrt(sum / data.length) * 3.2));
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();

      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        if (rafRef.current) cancelAnimationFrame(rafRef.current);
        setLevel(0);
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        handleAudio(blob);
      };
      mediaRecorderRef.current = recorder;
      setPhase("arming");
      await new Promise((r) => setTimeout(r, 650));
      if (mediaRecorderRef.current !== recorder) {
        stream.getTracks().forEach((tr) => tr.stop());
        return;
      }
      recorder.start();
      setPhase("recording");
    } catch {
      setError(t.micError);
      setPhase("idle");
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && phase === "recording") {
      mediaRecorderRef.current.stop();
      setPhase("transcribing");
    }
  }

  function toggleRecording() {
    if (phase === "recording") stopRecording();
    else if (phase === "idle") startRecording();
  }

  async function handleAudio(blob: Blob) {
    try {
      const form = new FormData();
      form.append("audio", blob, "question.webm");
      if (!autoDetect) form.append("language", selectedLang);
      const tRes = await fetch(`${API_BASE}/transcribe`, { method: "POST", body: form });
      if (!tRes.ok) throw new Error("transcribe");
      const tdata = await tRes.json();
      const question = (tdata.text || "").trim();
      setTranscript(question);
      if (!question) {
        setError(t.noCatch);
        setPhase("idle");
        return;
      }
      await askQuestion(question, true);
    } catch {
      setError(t.backendError);
      setPhase("idle");
    }
  }

  // Shared ask flow. speak=true also plays the spoken answer (voice mode);
  // speak=false just shows the text answer (text mode).
  async function askQuestion(question: string, speak: boolean) {
    try {
      setPhase("thinking");
      const aRes = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history: messages.slice(-6) }),
      });
      if (!aRes.ok) throw new Error("ask");
      const aData = await aRes.json();
      const replyText = aData.answer || "";
      // Commit the completed turn to the visible thread and clear the pending
      // question bubble.
      setMessages((prev) => [...prev, { question, answer: replyText }]);
      setTranscript("");
      setAnswer(replyText); // latest answer (drives the New-chat bar visibility)
      if (autoDetect && aData.language) {
        setDetectedLang(normalizeLang(aData.language));
      }

      // Auto-play aloud ONLY for voice-mode turns (speak=true). Text-mode turns
      // stay silent by default; the user taps that turn's own replay to hear it.
      if (!speak) {
        setPhase("idle");
        return;
      }
      await playText(replyText, messages.length); // index of the just-added turn
    } catch {
      setError(t.backendError);
      setPhase("idle");
    }
  }

  // Synthesize and play a specific message's text. Used by voice-mode auto-play
  // AND by every per-message replay button. It always re-fetches /speak for the
  // exact text passed in, so each replay plays ITS OWN message — the old design
  // shared one <audio> element and replayed whatever clip was last loaded.
  async function playText(text: string, idx: number) {
    if (!text) return;
    try {
      setPlayingIdx(idx);
      setIsPaused(false);
      setPhase("speaking");
      const sRes = await fetch(`${API_BASE}/speak?text=${encodeURIComponent(text)}`, { method: "POST" });
      const ttsType = sRes.headers.get("content-type") || "";
      if (!sRes.ok || !ttsType.includes("audio")) {
        setError(t.voiceUnavailable);
        setPhase("idle");
        setPlayingIdx(null);
        return;
      }
      const audioBlob = await sRes.blob();
      const url = URL.createObjectURL(audioBlob);
      if (audioRef.current) {
        audioRef.current.src = url;
        audioRef.current.onended = () => { setPhase("idle"); setPlayingIdx(null); setIsPaused(false); URL.revokeObjectURL(url); };
        audioRef.current.onerror = () => { setError(t.voiceUnavailable); setPhase("idle"); setPlayingIdx(null); URL.revokeObjectURL(url); };
        await audioRef.current.play();
      } else {
        setPhase("idle");
        setPlayingIdx(null);
      }
    } catch {
      setError(t.voiceUnavailable);
      setPhase("idle");
      setPlayingIdx(null);
    }
  }

  // Pause/resume the current playback.
  function togglePause() {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) { a.play(); setIsPaused(false); }
    else { a.pause(); setIsPaused(true); }
  }

  // Stop playback entirely and clear the controls.
  function stopAudio() {
    const a = audioRef.current;
    if (a) { a.pause(); a.currentTime = 0; }
    setIsPaused(false);
    setPlayingIdx(null);
    setPhase("idle");
  }

  function submitText() {
    const q = textInput.trim();
    if (!q || busy || phase === "arming") return;
    setError("");
    setTranscript(q);
    setAnswer("");
    setTextInput("");
    askQuestion(q, false);
  }

  function newChat() {
    if (busy || phase === "arming" || phase === "recording") return;
    if (audioRef.current) audioRef.current.pause();
    setMessages([]);
    setTranscript("");
    setAnswer("");
    setError("");
    setTextInput("");
    setPlayingIdx(null);
    setIsPaused(false);
  }

  const statusLabel: Record<Phase, string> = {
    idle: t.tapToAsk,
    arming: t.getReady,
    recording: t.speakNow,
    transcribing: t.reading,
    thinking: t.thinking,
    speaking: t.speaking,
  };

  const micScale = phase === "recording" ? 1 + level * 0.12 : 1;

  return (
    <main className="page" dir={rtl ? "rtl" : "ltr"}>
      <div className="aurora" aria-hidden="true" />

      <Link href="/" className="home-link">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
        </svg>
        {t.home}
      </Link>

      <header className="masthead">
        <span className="eyebrow">{t.eyebrow}</span>
        <h1>
          {t.title1}{t.titleAccent}
        </h1>
        <p className="sub">{t.sub}</p>
      </header>

      <div className="controls" ref={langRef}>
        <button
          type="button"
          className={`toggle ${autoDetect ? "on" : ""}`}
          onClick={() => phase === "idle" && setAutoDetect((v) => !v)}
          disabled={phase !== "idle"}
          role="switch"
          aria-checked={autoDetect}
        >
          <span className="toggle-track"><span className="toggle-thumb" /></span>
          <span className="toggle-label">{t.autoLabel}</span>
        </button>

        {!autoDetect && (
          <div className="lang-pick">
            <span className="lang-caption">{t.speakIn}</span>
            <button
              type="button"
              className={`lang-trigger ${langOpen ? "open" : ""}`}
              onClick={() => phase === "idle" && setLangOpen((o) => !o)}
              disabled={phase !== "idle"}
              aria-haspopup="listbox"
              aria-expanded={langOpen}
            >
              <span className="lang-current">
                {LANGUAGES.find((l) => l.name === selectedLang)?.native || selectedLang}
              </span>
              <span className="lang-chevron" aria-hidden="true">▾</span>
            </button>
            {langOpen && (
              <ul className="lang-menu" role="listbox">
                {LANGUAGES.map((l) => (
                  <li key={l.name} role="option" aria-selected={l.name === selectedLang}>
                    <button
                      type="button"
                      className={`lang-option ${l.name === selectedLang ? "selected" : ""}`}
                      onClick={() => { setSelectedLang(l.name); setLangOpen(false); }}
                    >
                      <span className="lang-native">{l.native}</span>
                      <span className="lang-english">{l.name}</span>
                      {l.name === selectedLang && <span className="lang-check" aria-hidden="true">✓</span>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="mode-tabs" role="tablist" aria-label="Input mode">
        <button
          role="tab"
          aria-selected={mode === "voice"}
          className={`mode-tab ${mode === "voice" ? "active" : ""}`}
          onClick={() => mode !== "voice" && !busy && phase === "idle" && setMode("voice")}
          disabled={busy || phase === "arming" || phase === "recording"}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="9" y="2" width="6" height="11" rx="3" /><path d="M5 10v1a7 7 0 0 0 14 0v-1" /><line x1="12" y1="18" x2="12" y2="22" />
          </svg>
          {t.voiceTab}
        </button>
        <button
          role="tab"
          aria-selected={mode === "text"}
          className={`mode-tab ${mode === "text" ? "active" : ""}`}
          onClick={() => mode !== "text" && !busy && phase === "idle" && setMode("text")}
          disabled={busy || phase === "arming" || phase === "recording"}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h10" />
          </svg>
          {t.textTab}
        </button>
      </div>

      {mode === "voice" ? (
        <section className="stage" aria-live="polite">
          <div className="mic-wrap" style={{ transform: `scale(${micScale})` }}>
            <button
              className={`mic mic--${phase}`}
              onClick={toggleRecording}
              disabled={busy || phase === "arming"}
              aria-label={phase === "recording" ? "Stop and send" : "Start speaking"}
            >
              <span className="ring ring1" />
              <span className="ring ring2" />
              <span className="ring ring3" />
              <span className="orb" />
              {phase === "arming" ? (
                <span className="ready-pulse" aria-hidden="true" />
              ) : phase === "recording" ? (
                <WaveGlyph level={level} />
              ) : (
                <MicGlyph spinning={phase === "transcribing" || phase === "thinking" || phase === "speaking"} />
              )}
            </button>
          </div>
          <p className={`status ${phase === "arming" ? "armed" : ""} ${phase === "recording" ? "live" : ""}`}>
            {statusLabel[phase]}
            {busy && <span className="dots"><i>.</i><i>.</i><i>.</i></span>}
          </p>
        </section>
      ) : (
        <section className="textbox-area">
          <div className="textbox">
            <textarea
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submitText();
                }
              }}
              placeholder={t.typePlaceholder}
              rows={1}
              disabled={busy}
              dir={rtl ? "rtl" : "ltr"}
            />
            <button
              className="send-btn"
              onClick={submitText}
              disabled={busy || !textInput.trim()}
              aria-label={t.send}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </section>
      )}

      {(messages.length > 0 || transcript || answer) && (
        <div className="newchat-bar">
          <button
            className="newchat-btn"
            onClick={newChat}
            disabled={busy || phase === "arming" || phase === "recording"}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" />
            </svg>
            {t.newChat}
          </button>
        </div>
      )}

      <section className="thread">
        {messages.map((m, i) => (
          <div key={i} className="turn">
            <div className="bubble bubble--you">
              <span className="who">{t.youAsked}</span>
              <p>{m.question}</p>
            </div>
            <div className="bubble bubble--eagle">
              <span className="who">
                {t.eagle}
                <button
                  className="replay"
                  onClick={() => playText(m.answer, i)}
                  disabled={busy || phase === "arming" || phase === "recording"}
                >▸ {t.replay}</button>
                {playingIdx === i && phase === "speaking" && (
                  <>
                    <button
                      className="replay"
                      onClick={togglePause}
                      aria-label={isPaused ? "Resume" : "Pause"}
                    >{isPaused ? "▶" : "❚❚"}</button>
                    <button
                      className="replay"
                      onClick={stopAudio}
                      aria-label="Stop"
                    >■</button>
                  </>
                )}
              </span>
              <p>{m.answer}</p>
            </div>
          </div>
        ))}
        {transcript && (
          <div className="bubble bubble--you">
            <span className="who">{t.youAsked}</span>
            <p>{transcript}</p>
          </div>
        )}
        {phase === "thinking" && (
          <div className="bubble bubble--eagle bubble--thinking" aria-live="polite" aria-label={t.thinking}>
            <span className="who">{t.eagle}</span>
            <span className="typing" aria-hidden="true"><i /><i /><i /></span>
          </div>
        )}
        {error && <div className="bubble bubble--error"><p>{error}</p></div>}
        <div ref={threadEndRef} />
      </section>

      <audio ref={audioRef} hidden />
      <footer className="foot">Florida Gulf Coast University</footer>
    </main>
  );
}

function MicGlyph({ spinning }: { spinning: boolean }) {
  return (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ position: "relative", animation: spinning ? "spin 1.4s linear infinite" : "none" }}>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </svg>
  );
}

function WaveGlyph({ level }: { level: number }) {
  const bars = [0.5, 0.85, 1, 0.7, 0.45];
  return (
    <div aria-hidden="true" style={{ position: "relative", display: "flex", alignItems: "center", gap: 4, height: 44 }}>
      {bars.map((b, i) => (
        <span key={i} style={{ width: 5, borderRadius: 4, background: "#fff", height: `${Math.max(8, b * (16 + level * 60))}px`, transition: "height 0.08s linear", animation: `eq 0.9s ${i * 0.08}s ease-in-out infinite` }} />
      ))}
    </div>
  );
}