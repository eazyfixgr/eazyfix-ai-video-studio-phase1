"""Provider-free template creation and safe, intentionally limited chat edits."""

from __future__ import annotations

import re

from .models import Project, sample_project


def create_from_prompt(prompt: str) -> Project:
    """Create a deterministic editable starter project without an API key."""
    project = sample_project()
    prompt_lower = prompt.lower()
    project.name = "Νέο διαφημιστικό"
    if any(word in prompt_lower for word in ("restaurant", "εστιατόρ", "φαγητ", "καφέ", "cafe")):
        project.name = "Διαφήμιση εστίασης"
        project.scenes[0].layers[1].text = "ΓΕΥΣΗ ΠΟΥ\nΜΕΝΕΙ ΑΞΕΧΑΣΤΗ"
        project.scenes[0].layers[2].text = "ΚΑΘΕ ΜΕΡΑ."
        project.scenes[1].layers[1].text = "ΦΡΕΣΚΑ ΥΛΙΚΑ\nΥΠΕΡΟΧΗ ΓΕΥΣΗ"
        project.scenes[2].layers[1].text = "ΕΛΑ ΝΑ\nΔΟΚΙΜΑΣΕΙΣ."
    elif any(word in prompt_lower for word in ("product", "προϊόν", "προϊον")):
        project.name = "Προϊοντική διαφήμιση"
        project.scenes[0].layers[1].text = "ΓΝΩΡΙΣΕ ΤΟ\nΝΕΟ ΑΓΑΠΗΜΕΝΟ"
        project.scenes[0].layers[2].text = "ΣΟΥ."
        project.scenes[1].layers[1].text = "ΣΧΕΔΙΑΣΜΕΝΟ\nΓΙΑ ΕΣΕΝΑ"
    match = re.search(r"(\d{1,3})\s*[- ]?\s*(?:seconds?|sec|δευτερόλεπτα|δευτερολεπτα|δευτ)\b", prompt_lower)
    if match:
        requested = min(60.0, max(5.0, float(match.group(1))))
        ratio = requested / project.duration
        for scene in project.scenes:
            scene.duration *= ratio
    if any(word in prompt_lower for word in ("landscape", "οριζόντι", "youtube")):
        project.width, project.height = 1920, 1080
    elif any(word in prompt_lower for word in ("square", "τετράγων")):
        project.width, project.height = 1080, 1080
    project.validate()
    return project


def apply_offline_edit(project: Project, prompt: str, selected_layer_id: str = "") -> tuple[str, bool]:
    """Apply only explicit edits that can be handled deterministically offline."""
    text = prompt.strip()
    lower = text.lower()
    layers = [(scene, layer) for scene in project.scenes for layer in scene.layers]
    selected = next(((scene, layer) for scene, layer in layers if layer.id == selected_layer_id), None)
    if selected and any(key in lower for key in ("bigger", "μεγαλ", "larger")):
        selected[1].font_size = min(180, selected[1].font_size + 8)
        return f"Μεγάλωσα το επιλεγμένο στοιχείο «{selected[1].role}».", True
    if selected and any(key in lower for key in ("smaller", "μικρότερ")):
        selected[1].font_size = max(14, selected[1].font_size - 8)
        return f"Μίκρυνα το επιλεγμένο στοιχείο «{selected[1].role}».", True
    is_text_edit = any(key in lower for key in ("change", "replace", "update", "edit", "άλλαξε", "αλλαξε", "γράψε", "γραψε", "κάνε", "κανε"))
    quote_pattern = r"[\"'“‘]([^\"'”’]+)[\"'”’]"
    quoted = list(re.finditer(quote_pattern, text))
    target_value = None
    new_match = re.search(r"\b(?:to|σε)\s*[\"'“‘](.+?)[\"'”’]", text, re.IGNORECASE)
    if new_match:
        target_value = new_match.group(1).strip()
    elif is_text_edit:
        unquoted = re.search(r"\b(?:to|σε)\s+(.+?)(?:\s+in\s+the\s+(?:first|second)\s+scene)?[.!?]*$", text, re.IGNORECASE)
        if unquoted:
            target_value = unquoted.group(1).strip().strip("\"'“”‘’")
    if is_text_edit and target_value and (selected or quoted or "headline" in lower or "τίτλ" in lower):
        target = None
        if ("second" in lower or "δεύτερ" in lower) and ("headline" in lower or "τίτλ" in lower):
            headlines = [(scene, layer) for scene, layer in layers if layer.kind == "text" and "headline" in layer.role]
            if len(headlines) > 1:
                target = headlines[1]
        if not target:
            old = next((match.group(1) for match in quoted if match.end() < (new_match.start() if new_match else len(text))), "")
            if old:
                target = next(((scene, layer) for scene, layer in layers if layer.kind == "text" and old.casefold() in layer.text.casefold()), None)
        if not target and ("first scene" in lower or "πρώτη σκην" in lower):
            first_scene = project.scenes[0]
            target = next(((first_scene, layer) for layer in first_scene.layers if layer.kind == "text"), None)
        if not target and selected and selected[1].kind == "text":
            target = selected
        if target:
            old_text = target[1].text
            target[1].text = target_value
            return f"Άλλαξα το κείμενο «{old_text[:32]}» στο «{target_value[:32]}».", True
    if "shorter" in lower or "λιγότερ" in lower or "shorten" in lower:
        project.scenes[-1].duration = max(1.5, project.scenes[-1].duration - 1)
        return "Μείωσα τη διάρκεια της τελευταίας σκηνής κατά 1 δευτερόλεπτο.", True
    if "quieter" in lower or "χαμηλότερ" in lower or "λιγότερο δυνατ" in lower:
        project.music_volume = max(0.0, project.music_volume * 0.65)
        return "Μείωσα την ένταση της μουσικής.", True
    if selected:
        return "Μπορώ να αλλάξω το κείμενο ή το μέγεθος του επιλεγμένου στοιχείου. Για τις υπόλοιπες αλλαγές χρησιμοποίησε τον inspector.", False
    return "Η τοπική λειτουργία δεν χρησιμοποιεί AI. Μπορείς να αλλάξεις κείμενο/μέγεθος επιλέγοντας στοιχείο ή να δημιουργήσεις ένα νέο βίντεο από prompt.", False
