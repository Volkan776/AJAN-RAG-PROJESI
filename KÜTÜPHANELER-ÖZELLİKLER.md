Kullanılan Kütüphaneler:
google-generativeai //
PyPDF2 //
gradio //
Pillow //
fpdf2 //

Bu proje, hukuk belgelerini (PDF ve JPG) analiz eden ve kullanıcıyla bu belgeler üzerine sohbet edebilen bir yapay zeka asistanıdır.

 ✨ Özellikler
- Multimodal Analiz:*Hem taranmış görselleri hem de metin dosyalarını işleyebilir. //
- Hukuki Odak: Karar özetleme ve avukatlara tavsiye sunma odaklı tasarım. //

-Öncelik sırası: 1.5-flash (hızlı/görsel), değilse 1.5-pro, o da yoksa ilk bulunan 

 if 'models/gemini-1.5-flash' in modeller:
 
 secilen_model = 'models/gemini-1.5-flash'
 
 elif 'models/gemini-pro' in modeller:
 
 secilen_model = 'models/gemini-pro'
 
 else:
 
 secilen_model = modeller[0]
