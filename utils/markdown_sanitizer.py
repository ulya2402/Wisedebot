import re

def sanitize_telegram_markdown_v1(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)

    # Simbol untuk Markdown V1 Telegram yang akan kita coba seimbangkan
    # '*' untuk bold, '_' untuk italic, '`' untuk inline code
    single_char_symbols = {'*', '_', '`'}
    code_block_tag = '```'

    # Karena ``` bisa mengandung *, _, ` di dalamnya yang tidak boleh diubah,
    # kita pisahkan dulu bagian dalam blok kode dan bagian luar.
    parts = text.split(code_block_tag)
    sanitized_parts = []

    for i, part in enumerate(parts):
        if i % 2 == 1: # Ini adalah bagian di dalam blok ```...```
            # Untuk konten di dalam blok kode, kita tidak melakukan sanitasi balancing,
            # hanya pastikan blok kodenya sendiri ditutup jika ini adalah bagian terakhir yang ganjil.
            sanitized_parts.append(part)
        else: # Ini adalah bagian di luar blok kode
            # Terapkan balancing untuk *, _, ` pada bagian ini
            stack = []
            current_segment_chars = []
            for char_in_part in part:
                if char_in_part in single_char_symbols:
                    if stack and stack[-1] == char_in_part: # Menutup tag
                        stack.pop()
                        current_segment_chars.append(char_in_part)
                    else: # Membuka tag baru
                        stack.append(char_in_part)
                        current_segment_chars.append(char_in_part)
                else:
                    current_segment_chars.append(char_in_part)

            # Tutup semua tag yang belum seimbang di akhir segmen ini
            while stack:
                current_segment_chars.append(stack.pop()) # Tambahkan tag penutup

            sanitized_parts.append("".join(current_segment_chars))

    # Gabungkan kembali semua bagian, pastikan ``` juga seimbang secara keseluruhan
    # Jika jumlah '```' ganjil, tambahkan satu di akhir
    result_text = code_block_tag.join(sanitized_parts)
    if text.count(code_block_tag) % 2 == 1:
        result_text += code_block_tag

    # Langkah tambahan: escape karakter '[' jika tidak membentuk link yang valid.
    # Ini lebih kompleks. Untuk sekarang, kita fokus pada balancing *, _, `.
    # Jika Anda masih mendapatkan error terkait '[', kita bisa tambahkan di sini.
    # Contoh sederhana untuk '[' (mungkin terlalu agresif):
    # result_text = result_text.replace("[", "\\[")

    return result_text
