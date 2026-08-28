# web_common

`web_common` contiene los componentes compartidos por `Browser`, `IA` y
`ArtBrowser`. Los proyectos siguen siendo aplicaciones independientes y
mantienen sus puntos de entrada; cada uno importa aquí solo las piezas que
necesita.

## Componentes principales

- `tabs.py`: pestañas WebEngine, ventanas emergentes con pestañas y menú
  contextual común (sonido y cierre de pestañas).
- `navbar.py`: barra de navegación, conversión de direcciones y guardado de
  páginas.
- `web_profiles.py`: creación de perfiles aislados de Qt WebEngine.
- `session.py`: restauración, metadatos y persistencia de sesiones.
- `local_viewer.py` y `folder_viewer.py`: archivos locales, carpetas,
  edición, Git y navegación dentro de archivos comprimidos.
- `video_tab.py` y `media_tabs.py`: visor local y helpers para abrir medios.
- `sidebar.py` y `downloader_handoff.py`: paneles compartidos y entrega de
  descargas al Downloader.

`downloader_handoff.py` también expone el handoff explícito de una URL actual.
Las ventanas pueden conectarlo a su barra sin interceptar navegación normal.

## Menú de pestañas

Usá `install_tab_context_menu()` desde la ventana que posee el
`QTabWidget`. La ventana sigue siendo responsable de cerrar sus widgets y de
mantener cualquier pestaña especial, como la pestaña `+`; el helper solo
construye las acciones comunes.

Los cambios en esta carpeta pueden afectar simultáneamente a los tres
navegadores. Conservá las importaciones relativas y la capacidad de ejecutar
cada aplicación directamente desde su propio directorio.
