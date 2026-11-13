# EazyFix AI Video Studio

Το **EazyFix AI Video Studio** είναι ένας επεξεργάσιμος desktop video editor για Windows. Η έκδοση 0.2.0 περιλαμβάνει scene-based editor, live preview, πραγματικό MP4/H.264 export, offline templates και αρχική DeepSeek AI orchestration με ασφαλείς, allow-listed project actions.

**Οδηγός χρήσης στα ελληνικά:** [USER_GUIDE_EL.md](USER_GUIDE_EL.md) — εξηγεί τη ροή από import και prompts μέχρι άμεση επεξεργασία, αποθήκευση, DeepSeek setup και export.

## Εκκίνηση στα Windows

1. Εγκατάστησε Python 3.11 ή νεότερο και FFmpeg. Το `ffmpeg.exe` πρέπει να είναι στο `PATH`.
2. Άνοιξε PowerShell στον φάκελο του project και εγκατέστησε τις βιβλιοθήκες:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Εκκίνησε την εφαρμογή:

   ```powershell
   python main.py
   ```

Για ελέγχους ανάπτυξης:

```powershell
python -m unittest discover -s tests -v
```

Για δημιουργία Windows executable:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

Προαιρετικά, για να συμπεριλάβεις FFmpeg που έχεις ήδη εγκαταστήσει:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\build_windows.ps1 -BundleFFmpeg
```

Το build δημιουργεί εκτελέσιμο κάτω από `dist\EazyFix AI Video Studio\`. Το FFmpeg δεν συμπεριλαμβάνεται από προεπιλογή και πρέπει να εγκατασταθεί ξεχωριστά. Μπορεί να συμπεριληφθεί με `-BundleFFmpeg`, εφόσον πρώτα ελεγχθούν οι άδειες χρήσης της συγκεκριμένης FFmpeg διανομής/codec build. Το executable δεν έχει υπογραφεί και δεν είναι installer.

## Βασική ροή

- Ξεκίνα από το ενσωματωμένο editable δείγμα `sample_projects/Website_Promo.eazyproj` ή το αρχικό 10-second project.
- Γράψε prompt στο chat για τοπική δημιουργία template. Η offline λειτουργία αναγνωρίζει βασικά θέματα, διάρκεια και aspect ratio.
- Πρόσθεσε JPG, PNG, WebP, SVG, ήχο ή video με **Προσθήκη media**, ή σύρε αρχεία στο παράθυρο. Τα πρωτότυπα αντιγράφονται στο local media store και δεν τροποποιούνται.
- Επίλεξε εικόνα και πάτησε **Place in scene**. Διπλό κλικ στο στοιχείο ανοίγει άμεση επεξεργασία κειμένου· μπορείς επίσης να το σύρεις στην προεπισκόπηση.
- Διπλό κλικ σε asset αλλάζει ρόλο/περιγραφή και αν προορίζεται για χρήση στο τελικό video. Τοποθέτηση audio asset ορίζει το background music.
- Επίλεξε σκηνή από το timeline για αλλαγή σειράς, διάρκεια, αντιγραφή ή διαγραφή. Οι αλλαγές είναι διαθέσιμες με Undo/Redo.
- Αποθήκευσε σε `.eazyproj`. Τα media αποθηκεύονται σε σχετικό `<project>_assets` sidecar folder.
- Πάτησε **Export MP4** για κανονικό H.264/AAC (όταν υπάρχει μουσική) αρχείο. Το export τρέχει σε background thread, δείχνει πρόοδο και ακυρώνεται.

## Project format

Τα `.eazyproj` είναι JSON με schema version, μεταδεδομένα, καμβά/FPS, assets, σκηνές, layers, σημασιολογικούς ρόλους, κείμενα, transforms, animation presets, transitions και audio/export settings. Τα layers παραμένουν επεξεργάσιμα· το renderer χρησιμοποιεί το ίδιο project model για preview και τελικό export. Κείμενο και εικόνες αποθηκεύονται ως στοιχεία, όχι flattened frames.

Οι project αλλαγές αποθηκεύονται στη μνήμη με έως 50 επίπεδα Undo/Redo. Γίνεται περιοδικό recovery autosave κάτω από `%LOCALAPPDATA%\EazyFixAIStudio\recovery.eazyproj` και προσφέρεται ανάκτηση στην επόμενη εκκίνηση.

## Τι λειτουργεί τώρα / τι ακολουθεί

### Phase 1 — διαθέσιμο

- PySide6 desktop UI με chat, preview/playback/scrubbing, inspector και scene cards.
- Δημιουργία ελληνικού editable promo template χωρίς API key.
- Import εικόνων, SVG, μουσικής και video αρχείων. Εικόνες τοποθετούνται και χρησιμοποιούνται στον renderer· ήχος μιξάρεται στο export. Τα video clips προς το παρόν αποθηκεύονται στη βιβλιοθήκη, αλλά δεν μπαίνουν ως moving footage στη σύνθεση.
- Text editing, βασικός άμεσος χειρισμός, animation presets, transitions, aspect ratios, project persistence, undo/redo και H.264/AAC export.
- Δείγμα project, automated tests και PyInstaller build script.

### Phase 2 — αρχική DeepSeek integration διαθέσιμη

- Provider settings με endpoint/model selection, `GET /models` capability discovery και connection test.
- DeepSeek Chat Completions για project planning και conversational edits, με `deepseek-v4-pro` για text και `deepseek-flash` για vision ως προεπιλογές που ανακτώνται/ελέγχονται από το API.
- Ρητή συγκατάθεση πριν χρησιμοποιηθεί provider, ξεχωριστή επιβεβαίωση κάθε φορά που θα σταλούν επιλεγμένες εικόνες, και API key στο OS credential store μέσω `keyring`.
- Δομημένα JSON plans που επικυρώνονται ως συγκεκριμένες project operations. Το μοντέλο δεν εκτελεί κώδικα/shell και μη έγκυρα actions απορρίπτονται ατομικά.
- Token usage εμφανίζεται όταν το επιστρέφει το API. Δεν γίνεται live API-key call στο test suite· οι provider contracts ελέγχονται με mocked/local tests.

### Δεν έχει υλοποιηθεί ακόμη

- Δεν υπάρχουν ακόμη OpenAI/Gemini/Ollama providers, TTS/narration ή AI-generated images/video.
- Δεν υπάρχει layered/keyframe timeline, beat detection, voiceover editor ή editing/caching σε επίπεδο scene.
- Η εισαγωγή video είναι library-only, όχι video compositing.
- Δεν έχει εκτελεστεί ακόμη Windows installer/signing/distribution pipeline.

Η DeepSeek API χρήση μπορεί να χρεώνεται σύμφωνα με την τρέχουσα τιμολόγηση του provider. Η εφαρμογή δεν υπολογίζει κόστος· έλεγξέ το στο DeepSeek Platform. Μην βάζεις κλειδιά API σε project αρχεία ή source code.

## Δομή κώδικα

- `eazyfix_studio/models.py` — validated project objects και schema.
- `eazyfix_studio/ai/` — DeepSeek HTTP client, image encoding, planning και strict action executor.
- `project_io.py` — project persistence, portable assets και recovery.
- `renderer.py`, `animations.py` — κοινός Pillow rendering/motion engine.
- `exporter.py` — cancelable FFmpeg worker.
- `assistant.py` — deterministic offline templates και περιορισμένες τοπικές edits.
- `ui/` — preview canvas, panels και main desktop workspace.
- `tests/` — unit tests για project model, persistence, renderer και offline workflow.
- `USER_GUIDE_EL.md` — οδηγίες end-user στα ελληνικά.
- `produce_v2.py` — το προϋπάρχον standalone video script, διατηρημένο ανεξάρτητα.
