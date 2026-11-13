# Εγχειρίδιο χρήσης — EazyFix AI Video Studio

Έκδοση εφαρμογής: **0.2.0**

## Τι κάνει

Το EazyFix AI Video Studio δημιουργεί κάθετα και οριζόντια διαφημιστικά video projects από επεξεργάσιμες σκηνές, κείμενα, εικόνες και μουσική. Δείχνει preview πριν από την εξαγωγή και παράγει πραγματικό MP4/H.264. Μπορεί να λειτουργήσει:

- **Τοπικά, χωρίς AI ή API key:** με ενσωματωμένο template και απλές, περιορισμένες εντολές.
- **Με DeepSeek:** για κατανόηση φυσικής γλώσσας, επιλογή σκηνών/κειμένων/εικόνων και εφαρμογή στοχευμένων αλλαγών.

Το AI δεν δημιουργεί απευθείας το MP4 και δεν εκτελεί κώδικα. Επιστρέφει μόνο συγκεκριμένες ενέργειες, όπως αλλαγή κειμένου ή τοποθέτηση εικόνας. Η εφαρμογή ελέγχει κάθε ενέργεια και ενημερώνει το επεξεργάσιμο project.

## Εκκίνηση

### Με το Windows executable

Άνοιξε:

```text
dist\EazyFix AI Video Studio\EazyFix AI Video Studio.exe
```

Για MP4 export πρέπει να είναι εγκατεστημένο το FFmpeg και το `ffmpeg.exe` να βρίσκεται στο `PATH`. Η έκδοση executable που δημιουργείται από το build δεν περιλαμβάνει FFmpeg από προεπιλογή.

### Από τον πηγαίο κώδικα

```powershell
python -m pip install -r requirements.txt
python main.py
```

Για export χρειάζεται επίσης το FFmpeg. Αναλυτικές οδηγίες build υπάρχουν στο `README.md`.

## Γνωριμία με το παράθυρο

- **Πάνω γραμμή:** New, Open, Save, Undo, Redo, AI Settings, Inspector και Export MP4.
- **Αριστερά — AI Chat:** γράφεις prompt και βλέπεις απαντήσεις, πρόοδο, αποτυχίες και retry.
- **Media Library:** εικόνες, λογότυπα, audio και video assets που έχουν εισαχθεί στο project.
- **Κέντρο — Live Preview:** preview, Play/Pause, scrubber, ποιότητα preview, aspect ratio και fullscreen.
- **Κάτω — Scenes:** κάρτες σκηνών, διάρκεια, προσθήκη/αντιγραφή/διαγραφή και αλλαγή σειράς.
- **Inspector:** εμφανίζεται όταν επιλέξεις στοιχείο ή πατήσεις Inspector. Οι ιδιότητες εξαρτώνται από τον τύπο του στοιχείου.

Το αρχικό project είναι ένα επεξεργάσιμο, ελληνικό promo 10 δευτερολέπτων. Μπορείς επίσης να ανοίξεις το `sample_projects/Website_Promo.eazyproj`.

## Γρήγορη δημιουργία βίντεο

1. **Εισήγαγε υλικό.** Πάτησε `＋ Import` ή `＋ Προσθήκη media`, ή σύρε αρχεία στο παράθυρο. Επιτρέπονται JPG/JPEG, PNG, WebP, GIF, BMP, SVG, audio και video.
2. **Συμπλήρωσε πληροφορίες assets.** Κάνε διπλό κλικ σε thumbnail και όρισε ρόλο, περιγραφή και αν προορίζεται για το τελικό video. Τα πρωτότυπα δεν τροποποιούνται· αντιγράφονται στον τοπικό χώρο εργασίας της εφαρμογής.
3. **Επίλεξε αναλογία.** Από το preview toolbar διάλεξε Portrait 9:16, Landscape 16:9 ή Square 1:1.
4. **Περιέγραψε το αποτέλεσμα.** Για παράδειγμα:

   > Create a professional 20-second portrait ad for my website business. Use my logo and the two client screenshots. Write Greek headlines and finish with a contact call to action.

5. **Έλεγξε το preview.** Χρησιμοποίησε Play/Pause και τον scrubber για να δεις όλο το βίντεο ή επίλεξε σκηνή από το timeline.
6. **Κάνε αλλαγές.** Ζήτησέ τες στο chat ή επεξεργάσου στοιχεία απευθείας.
7. **Αποθήκευσε και εξήγαγε.** Πάτησε Save για `.eazyproj` και Export MP4 για το τελικό video.

### Χρήση χωρίς API key

Το `LOCAL MODE` δημιουργεί τοπικό template χωρίς αποστολή δεδομένων σε AI provider. Αναγνωρίζει μερικά βασικά θέματα, διάρκεια και αναλογία εικόνας. Μπορεί επίσης να εκτελέσει περιορισμένες εντολές, όπως αλλαγή του επιλεγμένου κειμένου, μεγέθυνση στοιχείου, μείωση διάρκειας ή χαμήλωμα μουσικής. Για ακριβή επεξεργασία χρησιμοποίησε τον Inspector.

Η τοπική λειτουργία **δεν είναι AI** και δεν καταλαβαίνει ελεύθερα όλες τις οδηγίες.

## Σύνδεση DeepSeek

1. Δημιούργησε API key στον [DeepSeek Platform](https://platform.deepseek.com/api_keys).
2. Πάτησε **AI Settings** και επίλεξε **DeepSeek API**.
3. Άφησε το επίσημο endpoint `https://api.deepseek.com`, εκτός αν έχεις συγκεκριμένη συμβατή υπηρεσία.
4. Επικόλλησε το API key. Δεν εμφανίζεται ξανά μετά την αποθήκευση· φυλάσσεται στο **Windows Credential Manager**, όχι στο project ή στο settings JSON.
5. Ενεργοποίησε τη συγκατάθεση για αποστολή prompts και project summaries, πάτησε **Test connection** και μετά **Save**.

Τα προεπιλεγμένα μοντέλα ακολουθούν τα επίσημα DeepSeek docs που ελέγχθηκαν για την έκδοση 0.2.0:

- `deepseek-v4-pro` για κείμενο και planning.
- `deepseek-flash` για vision και εικόνες.

Το **Test connection** διαβάζει το `/models` και εμφανίζει τις πραγματικές δυνατότητες που επιστρέφει ο λογαριασμός. Μπορείς να αλλάξεις μοντέλα/endpoint από τις ρυθμίσεις. Οι οδηγίες DeepSeek ενημερώνονται ανεξάρτητα από την εφαρμογή: [API quick start](https://api-docs.deepseek.com/), [models](https://api-docs.deepseek.com/api/list-models), [vision](https://api-docs.deepseek.com/guides/vision), [JSON output](https://api-docs.deepseek.com/guides/json_mode).

### Τι αποστέλλεται στο DeepSeek

- Όταν είναι ενεργό το DeepSeek, αποστέλλονται το prompt και μια σύνοψη του project (σκηνές, κείμενα, ρόλοι και περιγραφές assets).
- Οι εικόνες **δεν αποστέλλονται αυτόματα**. Επίλεξε έως έξι εικόνες στη Media Library και, όταν σταλεί αίτημα, επιβεβαίωσε ξεχωριστά το παράθυρο αποστολής.
- Στέλνονται μόνο οι επιλεγμένες εικόνες. Για ανάλυση η εφαρμογή δημιουργεί προσωρινό, μειωμένο αντίγραφο· δεν αλλάζει τα πρωτότυπα.
- Η εφαρμογή εμφανίζει αριθμό tokens όταν τον επιστρέφει το API. Δεν υπολογίζει κόστος· έλεγξε την τρέχουσα τιμολόγηση στο DeepSeek Platform.
- Αν δεν επιβεβαιώσεις εικόνες, μπορείς να συνεχίσεις με text-only αίτημα. Η σύνοψη και το prompt αποστέλλονται μόνο αφού ενεργοποιήσεις και επιβεβαιώσεις τον provider.

## Άμεση επεξεργασία

### Κείμενο

- Κάνε κλικ σε κείμενο στο preview για να επιλεγεί και να ανοίξει ο Inspector.
- Πάτησε το πεδίο **Text** για αλλαγή, επίλεξε μέγεθος, χρώμα, animation και θέση.
- Κάνε διπλό κλικ στο κείμενο για γρήγορη επεξεργασία σε παράθυρο.
- Σύρε το στοιχείο στο preview για να αλλάξεις τη θέση του.
- Διαθέσιμα entrance presets: `fade`, `fade_up`, `zoom`, `slide_left`, `spring`, `word_reveal`.

### Εικόνες και αντικατάσταση

- Επίλεξε thumbnail και πάτησε **Place in scene** για να προστεθεί στην επιλεγμένη σκηνή.
- Για αντικατάσταση, επίλεξε την εικόνα στο preview, άνοιξε τον Inspector και διάλεξε άλλο **Image asset**. Η θέση, το μέγεθος και το animation της υπάρχουσας εικόνας διατηρούνται.
- Σύρε την εικόνα στο preview για να αλλάξεις θέση.

### Σκηνές

Επίλεξε κάρτα σκηνής στο timeline. Τα κουμπιά επιτρέπουν:

- `− 1s` / `＋ 1s`: μείωση/αύξηση διάρκειας.
- `＋ Scene`: προσθήκη σκηνής.
- `Duplicate`: αντιγραφή της επιλεγμένης σκηνής.
- `↑` / `↓`: αλλαγή σειράς.
- `Delete`: διαγραφή. Το project πρέπει να κρατήσει τουλάχιστον μία σκηνή.

Με `Ctrl+Z` κάνεις Undo και με `Ctrl+Y` Redo. Οι AI αλλαγές εμφανίζονται ως ξεχωριστές, αναστρέψιμες ενέργειες.

### Μουσική

Εισήγαγε MP3, WAV, M4A, AAC ή OGG. Επίλεξε το audio thumbnail και πάτησε **Place in scene** για να οριστεί ως background music. Το MP4 export εφαρμόζει ένταση και fade in/out και κωδικοποιεί ήχο σε AAC. Αν δεν έχει οριστεί μουσική, το export είναι χωρίς audio track.

## Αποθήκευση και export

- Τα `.eazyproj` είναι JSON project αρχεία με editable κείμενα, layers, assets, σκηνές, animations, transitions και audio settings.
- Μαζί με το project αποθηκεύεται φάκελος `<όνομα-project>_assets`. Για μεταφορά σε άλλον υπολογιστή, κράτησε **και τα δύο**.
- Η εφαρμογή κάνει recovery autosave περίπου κάθε 45 δευτερόλεπτα στο `%LOCALAPPDATA%\EazyFixAIStudio\recovery.eazyproj` και προτείνει ανάκτηση στην επόμενη εκκίνηση.
- Πάτησε **Export MP4**, διάλεξε διαδρομή και περίμενε την πρόοδο. Το export τρέχει σε background thread και το `Cancel` σταματά την εργασία.
- Διαθέσιμες αναλογίες: portrait 1080×1920, landscape 1920×1080 και square 1080×1080. Το output είναι H.264/yuv420p· με μουσική χρησιμοποιείται AAC.
- Η ταχύτητα εξαρτάται από CPU, ανάλυση, διάρκεια και FFmpeg. Το preview δεν είναι το τελικό export.

## Συνομιλιακές αλλαγές

Όταν είναι ενεργό το DeepSeek, μπορείς να ζητήσεις στοχευμένες αλλαγές, για παράδειγμα:

- “Change the second headline to ‘Ιστοσελίδες στα μέτρα σου’.”
- “Replace the image in Scene 2 with the selected screenshot.”
- “Make this headline bigger.”
- “Make the transitions in Scene 2 faster.”
- “Add a closing contact scene with the text …”
- “Make the music quieter.”

Οι αλλαγές που υποστηρίζονται από το project engine είναι: νέα δημιουργία project, αλλαγή συγκεκριμένου κειμένου, διάρκεια σκηνής, αναλογία, ένταση μουσικής, transition/animation, τοποθέτηση ή αντικατάσταση εικόνας και προσθήκη/αντιγραφή/διαγραφή σκηνής. Αν το AI επιστρέψει μη έγκυρη ή μη επιτρεπτή ενέργεια, η εφαρμογή δεν την εκτελεί και δεν κρατά μερική αλλαγή.

## Τι δεν κάνει ακόμη

- Τα εισαγόμενα video clips εμφανίζονται στη βιβλιοθήκη αλλά δεν συντίθενται ως κινούμενο footage.
- Δεν υπάρχει πολυεπίπεδο/keyframe timeline, waveform editor, beat detection, TTS/voiceover ή AI image/video generation.
- Τα chat edits είναι περιορισμένα στις διαθέσιμες project actions· σύνθετες αλλαγές γίνονται από τον Inspector ή απαιτούν μελλοντικές δυνατότητες.
- Η εφαρμογή δεν εμφανίζει υπολογισμό κόστους provider.

## Αντιμετώπιση προβλημάτων

| Πρόβλημα | Τι να ελέγξεις |
|---|---|
| Το export γράφει ότι δεν βρίσκει FFmpeg | Εγκατάστησε FFmpeg και πρόσθεσε το `ffmpeg.exe` στο `PATH`. Κλείσε και ξανάνοιξε την εφαρμογή. |
| Το Test connection αποτυγχάνει | Έλεγξε σύνδεση Internet, API key, endpoint `https://api.deepseek.com` και status του provider. |
| Το AI δεν αναλύει εικόνες | Έλεγξε ότι επίλεξες εικόνες, επιβεβαίωσες το upload και ότι το vision model έχει capability `image`. |
| Δεν αποθηκεύεται το API key | Χρειάζεται Windows Credential Manager και εγκατεστημένο το `keyring`. Η εφαρμογή δεν γράφει το key σε απλό αρχείο. |
| Λείπει εικόνα μετά το άνοιγμα project | Μετέφερε μαζί με το `.eazyproj` τον φάκελο `<όνομα-project>_assets`. |
| Το preview είναι αργό ή χαμηλής ποιότητας | Επίλεξε `Draft preview`. Το τελικό export παράγεται στην επιλεγμένη πλήρη ανάλυση. |
