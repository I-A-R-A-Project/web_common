# web_common

`web_common` contiene los componentes compartidos por `Browser`, `IA` y
`ArtBrowser`. Los proyectos siguen siendo aplicaciones independientes y
mantienen sus puntos de entrada; cada uno importa aquí solo las piezas que
necesita.

## Componentes principales

- `tabs.py`: pestañas WebEngine, ventanas emergentes con pestañas y menú
  contextual común (sonido y cierre de pestañas), incluida la configuración
  del ciclo de vida del `QTabWidget` mediante `configure_tab_widget()`.
- `navbar.py`: barra de navegación, conversión de direcciones y guardado de
  páginas.
- `web_profiles.py`: creación de perfiles aislados de Qt WebEngine.
- `session.py`: restauración, metadatos y persistencia de sesiones.
- `local_viewer.py` y `folder_viewer.py`: archivos locales, carpetas,
  edición, Git y navegación dentro de archivos comprimidos. `archive_entries()`
  lista contenidos y `extract_archive()` extrae ZIP, TAR/GZIP/BZIP2 y, cuando
  están instaladas sus dependencias opcionales, RAR/7z.
- `video_tab.py`, `epub_tab.py` y `media_tabs.py`: visores locales y helpers
  para abrir medios.
- `sidebar.py` y `downloader_handoff.py`: paneles compartidos y entrega de
  descargas al Downloader.
- `navigation.py`: ajuste y restablecimiento del zoom de la vista activa,
  pestaña activa, activación de la pestaña `+`, sincronización
  de la barra de dirección y carga de URLs con callbacks específicos.
- `assets/epub_reader.html`, `epub_reader.css` y `epub_reader.js`: plantilla
  y comportamiento del lector EPUB, separados del código Python.
- `tabs.py` también expone `close_tab()`, que centraliza el cierre seguro,
  selección de la pestaña anterior y recreación de una pestaña cuando solo
  queda `+`; cada aplicación inyecta su limpieza particular.

`downloader_handoff.py` también expone el handoff explícito de una URL actual.
Las ventanas pueden conectarlo a su barra sin interceptar navegación normal.

`IA` y `Browser` deben mantener en sus ventanas únicamente los callbacks y
metadatos propios de cada aplicación. La creación de pestañas, la barra `+`,
el cierre seguro, el reordenado y los eventos comunes se conectan mediante
`configure_tab_widget()`. Los gestores de perfiles, sesiones de negocio,
descargas, colecciones, historial y páginas de inicio siguen siendo
específicos de cada aplicación.

## Menú de pestañas

Usá `install_tab_context_menu()` desde la ventana que posee el
`QTabWidget`. La ventana sigue siendo responsable de cerrar sus widgets y de
mantener cualquier pestaña especial, como la pestaña `+`; el helper solo
construye las acciones comunes.

Los cambios en esta carpeta pueden afectar simultáneamente a los tres
navegadores. Conservá las importaciones relativas y la capacidad de ejecutar
cada aplicación directamente desde su propio directorio.
