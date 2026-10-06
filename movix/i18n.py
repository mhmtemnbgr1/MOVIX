"""Arayüz ve mesaj dili (Türkçe / English). t("anahtar", ...) seçili dilde metni verir; dil ayarı kaydedilir."""
from __future__ import annotations

import locale

LANGS = {"tr": "Türkçe", "en": "English"}
_lang: list = [None]

STRINGS: dict[str, dict[str, str]] = {
    "tr": {
        # --- Üst çubuk
        "app_subtitle": "Hazır 3B karakterlerden 2B oyun animasyonları",
        "pick_blender": "Blender seç…",
        "claude_ready": "● Claude hazır", "claude_missing": "● Claude Code yok",
        "blender_missing": "● Blender bulunamadı", "blender_opening": "● Blender açılıyor…",
        "blender_failed": "● Blender bağlanamadı", "blender_ok": "● Blender bağlı",
        "blender_not_installed": "Blender kurulu değil ya da bulunamadı. 'Blender seç…' ile blender.exe'yi göster ya da winget install BlenderFoundation.Blender.LTS.4.5",
        "lang_button": "🌐  EN", "dialog_blender": "blender.exe seç", "all_files": "Tümü",
        # --- Sol panel
        "sec1_title": "Karakter isteği",
        "sec1_hint": "Hazır bir karakter temel alınır; parçaları karıştırılır, renkleri (ten, saç, kıyafet) boyanır ve vücut oranı ayarlanarak istediğin karaktere yaklaştırılır.",
        "placeholder": "Örn. kırmızı pelerinli bir şövalye, yeşil cübbeli büyücü, sinsi bir hırsız…",
        "suggest": "★  3 karakter öner", "direct": "Direkt yap",
        "sec2_title": "Değişiklik iste", "sec2_hint": "Beğenmediğin yeri yaz: örn. “pelerini kaldır, mavi yap”.", "apply": "Uygula",
        "make": "Blender'da yap  →",
        "ready": "Hazır.",
        # --- Sağ panel
        "animations": "Animasyonlar",
        "anim_walk_right": "Sağa yürüme", "anim_walk_left": "Sola yürüme", "anim_idle": "Sabit durma",
        "frames_fps": "%d kare · %d fps",
        "empty": "Henüz karakter yok. Soldan bir istek yaz, 3 öneriden birini seç; Claude hazır karakteri Blender'da senin için özelleştirsin.",
        "open_folder": "📂  Klasörü aç", "open_blender": "Blender'da aç", "saved": "Kayıtlı",
        "live": "Canlı akış", "live_sub": "ne yapılıyor?", "clear": "Temizle", "character": "karakter",
        # --- Durum mesajları
        "thinking": "Claude 3 karakter fikri düşünüyor…", "working": "Claude Blender'da çalışıyor…",
        "cancel": "✕ İptal", "cancelling": "İptal ediliyor…", "cancelled": "İptal edildi.", "error": "HATA: ",
        "busy_wait": "Şu an bir iş sürüyor, bitmesini bekle (ya da İptal).", "busy_ignored": "Tıklandı ama bir iş zaten sürüyor; yok sayıldı.",
        "claude_not_found": "Claude Code bulunamadı. Kurulum: https://claude.com/claude-code", "claude_not_found_log": "Claude Code bulunamadı.",
        "pick_one": "Birini seç; Claude karakteri Blender'da hazırlasın.",
        "describe_first": "Önce karakteri tarif et.",
        "blender_not_connected": "Blender bağlı değil. Üstten 'Blender seç…' ile başlat.", "blender_not_connected_log": "Blender bağlı değil, iş başlatılmadı.",
        "log_change": "DEĞİŞİKLİK: %s", "log_started": "BAŞLADI: %s",
        "done_status": "✔ Bitti: %s (%s). Blender'da hazırlandı.", "log_done": "BİTTİ: %s · %s · kaydedildi: %s", "summary": "Claude özeti: ",
        "need_character": "Önce bir karakter yap ya da kayıtlı birini aç.",
        # --- Üretim hattı
        "need_folder": "değişiklik için mevcut klasör gerekir",
        "prep_scene": "Blender sahnesi hazırlanıyor…",
        "missing_parts": "Karakterde eksik parça var (kafa, gövde, kol veya bacak). Tekrar dene.",
        "making_anims": "Animasyonlar oluşturuluyor…",
        "rendering": "Animasyon kareleri çiziliyor (sağa yürüme, sola yürüme, sabit durma)…",
        # --- Claude çalıştırıcı
        "runner_not_found": "Claude Code bulunamadı. Kurulum: https://claude.com/claude-code",
        "runner_timeout": "Claude %d dakikada bitiremedi, durduruldu. Tekrar dene.",
        "runner_no_ideas": "Claude fikir üretmedi (cevap: %s). Tekrar dene.", "runner_empty": "boş",
        "runner_error": "Claude hata verdi.",
        "runner_closed": "Claude cevap vermeden kapandı. Giriş yaptığından emin ol (claude auth login).",
        "prog_code": "Claude karakteri hazırlıyor… (kod adımı %d)", "prog_preview": "Claude Blender'da çizimi kontrol ediyor… (önizleme %d)",
        "prog_scene": "Claude sahneyi inceliyor…",
        "limit_reached": "Adım/süre sınırına ulaşıldı (%d adım, %d sn). Karakter mevcut haliyle tamamlanıyor…", "repairing": "Eksik parçalar yerine konuyor…",
        # --- Blender istemcisi
        "bl_closed": "Blender bağlantıyı kapattı", "bl_connect": "Blender'a bağlanılamadı: %s",
        "bl_exited": "Blender kendiliğinden kapandı", "bl_timeout": "Blender %d saniyede hazır olmadı",
    },
    "en": {
        "app_subtitle": "2D game animations from ready-made 3D characters",
        "pick_blender": "Choose Blender…",
        "claude_ready": "● Claude ready", "claude_missing": "● Claude Code missing",
        "blender_missing": "● Blender not found", "blender_opening": "● Blender starting…",
        "blender_failed": "● Blender could not connect", "blender_ok": "● Blender connected",
        "blender_not_installed": "Blender is not installed or could not be found. Use 'Choose Blender…' to point to blender.exe, or run: winget install BlenderFoundation.Blender.LTS.4.5",
        "lang_button": "🌐  TR", "dialog_blender": "Select blender.exe", "all_files": "All files",
        "sec1_title": "Character request",
        "sec1_hint": "A ready-made character is the starting point; its parts are mixed, its colours (skin, hair, clothes) painted and its body shape adjusted to get close to what you asked for.",
        "placeholder": "E.g. a knight in a red cape, a wizard in a green robe, a sneaky thief…",
        "suggest": "★  Suggest 3 characters", "direct": "Build directly",
        "sec2_title": "Request a change", "sec2_hint": "Describe what to change, e.g. “remove the cape, make it blue”.", "apply": "Apply",
        "make": "Build in Blender  →",
        "ready": "Ready.",
        "animations": "Animations",
        "anim_walk_right": "Walk right", "anim_walk_left": "Walk left", "anim_idle": "Idle",
        "frames_fps": "%d frames · %d fps",
        "empty": "No character yet. Write a request on the left and pick one of the 3 ideas; Claude will customise a ready-made character in Blender for you.",
        "open_folder": "📂  Open folder", "open_blender": "Open in Blender", "saved": "Saved",
        "live": "Live log", "live_sub": "what's happening?", "clear": "Clear", "character": "character",
        "thinking": "Claude is thinking of 3 character ideas…", "working": "Claude is working in Blender…",
        "cancel": "✕ Cancel", "cancelling": "Cancelling…", "cancelled": "Cancelled.", "error": "ERROR: ",
        "busy_wait": "A job is running, wait for it to finish (or cancel).", "busy_ignored": "Clicked while a job was already running; ignored.",
        "claude_not_found": "Claude Code not found. Install: https://claude.com/claude-code", "claude_not_found_log": "Claude Code not found.",
        "pick_one": "Pick one; Claude will build the character in Blender.",
        "describe_first": "Describe the character first.",
        "blender_not_connected": "Blender is not connected. Start it with 'Choose Blender…' above.", "blender_not_connected_log": "Blender is not connected, job not started.",
        "log_change": "CHANGE: %s", "log_started": "STARTED: %s",
        "done_status": "✔ Done: %s (%s). Built in Blender.", "log_done": "DONE: %s · %s · saved: %s", "summary": "Claude summary: ",
        "need_character": "Build a character first or open a saved one.",
        "need_folder": "an existing folder is required for a change",
        "prep_scene": "Preparing the Blender scene…",
        "missing_parts": "The character is missing a part (head, body, arm or leg). Try again.",
        "making_anims": "Creating animations…",
        "rendering": "Rendering animation frames (walk right, walk left, idle)…",
        "runner_not_found": "Claude Code not found. Install: https://claude.com/claude-code",
        "runner_timeout": "Claude did not finish within %d minutes and was stopped. Try again.",
        "runner_no_ideas": "Claude produced no ideas (reply: %s). Try again.", "runner_empty": "empty",
        "runner_error": "Claude reported an error.",
        "runner_closed": "Claude closed without answering. Make sure you are signed in (claude auth login).",
        "prog_code": "Claude is customising the character… (code step %d)", "prog_preview": "Claude is checking the preview in Blender… (preview %d)",
        "prog_scene": "Claude is inspecting the scene…",
        "limit_reached": "Step/time limit reached (%d steps, %d s). Finishing the character as it is…", "repairing": "Putting back missing parts…",
        "bl_closed": "Blender closed the connection", "bl_connect": "Could not connect to Blender: %s",
        "bl_exited": "Blender exited on its own", "bl_timeout": "Blender was not ready after %d seconds",
    },
}


def detect() -> str:
    """Kayıtlı ayar, yoksa sistem dili (Türkçe ise tr, değilse en)."""
    try:
        from . import config
        saved = config.load_settings().get("lang")
        if saved in LANGS:
            return saved
    except Exception:  # noqa: BLE001
        pass
    try:
        loc = (locale.getlocale()[0] or "").lower()
    except Exception:  # noqa: BLE001
        loc = ""
    return "tr" if loc.startswith("tr") else "en"


def get_lang() -> str:
    if _lang[0] is None:
        _lang[0] = detect()
    return _lang[0]


def set_lang(code: str, persist: bool = True) -> None:
    if code not in LANGS:
        raise ValueError("desteklenmeyen dil: %s" % code)
    _lang[0] = code
    if persist:
        from . import config
        data = config.load_settings()
        data["lang"] = code
        config.save_settings(data)


def lang_name() -> str:
    """Claude'a verilen yönergelerde çıktı dili adı."""
    return "TURKISH" if get_lang() == "tr" else "ENGLISH"


def t(key: str, *args) -> str:
    table = STRINGS.get(get_lang(), STRINGS["en"])
    text = table.get(key) or STRINGS["en"].get(key) or key
    return text % args if args else text

