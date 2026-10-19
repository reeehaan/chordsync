# Bundled fonts

The Golden Hour theme uses two fonts from Google Fonts, both under the SIL Open
Font License 1.1 (full texts in `mobile/assets/fonts/*-OFL.txt`). They may be
bundled and used in the app, including commercially, but not sold on their own.

| Family | Use | Source |
| --- | --- | --- |
| Newsreader | song titles and lyrics | `google/fonts` `ofl/newsreader` |
| DM Sans | controls and instructional text | `google/fonts` `ofl/dmsans` |

The Google files are variable fonts. Static weights 400, 500, 600, 700 and 800
were cut from them with fontTools' instancer (optical size fixed at 16 for
Newsreader and 14 for DM Sans), because Flutter on iOS maps `FontWeight` to
static files more reliably than to a variable axis. Neither font has Sinhala
glyphs, so Sinhala text is drawn with the system font.
