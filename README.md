# Sublime ENSIME

This project provides integration with ENSIME and Sublime Text Editor 2.
It's a fork of the original sublime-ensime project, written by Ivan Porto Carrero.
This fork introduces additional features, stability improvements, user-friendly setup and error messages,
better logging.

Sublime ENSIME strives to realize the dream of having Scala semantic services
inside a lightning fast and feature-rich text editor. Big thanks to Aemon Cannon,
Daniel Spiewak and Ivan Porto Carrero who demonstrated that this vision is possible
and inspired us to kick off the project.

## Project status

This is a beta version. Basic things will work (for example, error highlighting),
but there might still be problems. Please submit issues to our tracker
if you catch SublimeScala misbehaving: https://github.com/sublimescala/sublime-ensime/issues/new.

## Features

* Natively targets Scala 2.10.x, also supports Scala 2.9.x.

* Creates and understands `.ensime` projects (maximum one project per Sublime window,
  if you have a project with multiple subprojects only a single subproject will be available at a time).

* Integrates with SBT to generate Ensime projects from SBT projects and provides
  a command, which runs SBT compilation for the current Ensime project.

* Once your Ensime project is configured (we have a helper for that) and Ensime is run,
  Scala files in that Ensime project benefit from a number of semantic services:

    * On-the-fly typechecking and error highlighting on save. Error messages are displayed
      in the status bar when you click highlighted regions (unfortunately, Sublime Text 2 doesn't
      support programmable tooltips). Moreover, errors can be viewed in a dynamically updated buffer
      displayed with `Tools > Ensime > Commands > Show notes`.

    * Type-aware completions for identifiers (integrates into the built-in mechanism of completions
      in Sublime Text 2, depending on your configuration it might be bound to `Ctrl+Space`/`Cmd+Space` or `Tab`).

    * Type-aware go to definition (implemented by `ensime_go_to_definition` command: bind it yourself
      to your favorite hotkey or use the default `Ctrl+Click` binding on Windows/Linux or `Cmd+Click` on Mac).

* Implements experimental support for debugging. At the moment you can set breakpoints, create launch
  configurations, step through programs in the debugger, inspect program output, navigate stack traces
  and watch values of local variables. Things are far from smooth, but it might be worth a try.

## How to install?

1. Install the package itself:

    a. If you use [Package Control](http://wbond.net/sublime_packages/package_control), install package Ensime.
    (`Preferences > Package Control > Install Package > Ensime`).

    b. Otherwise install manually.
       In your Sublime Text `Packages` directory, invoke:

    ```
    git clone git://github.com/sublimescala/sublime-ensime.git Ensime
    ```

    You can find the `Packages` directory by opening Sublime, selecting `View > Show Console`
    and then running the `sublime.packages_path()` command.
    Make sure you're using the right directory, or the plugin won't work.

2. Install the ENSIME server:

    Download Ensime from http://download.sublimescala.org.
    The archive will contain a directory with an Ensime version.
    
    Make sure to download the build which matches your Scala version.
    The primary development platform of Ensime is 2.10.x, but 2.9.x is supported as well
    (though availability of builds of 2.9.x might lag behind). Every once in a while,
    the plugin might undergo updates which will require fresh Ensime builds. If there's
    no 2.9.x build of required version, please [ping us](https://github.com/sublimescala/sublime-ensime/issues/68)
    or compile Ensime from sources (it's as easy as running `sbt ++2.9.2 package`).

    Extract the contents of this directory into the `server` subdirectory
    of just created `Ensime` directory. If you do everything correctly,
    `Ensime/server/bin` will contain Ensime startup scripts and
    `Ensime/server/lib` will contain Ensime binaries.

3. (Re)start Sublime Text editor.

4. Configure Ensime.

    a. Use `Preferences > Package Settings > Ensime` (Windows/Linux) or
       `Sublime Text 2 > Preferences > Package Settings > Ensime` (Mac)
       to configure different aspects of this plugin.

    b. By default Ensime customizes mouse bindings. It makes
       `Ctrl+Click`/`Cmd+Click` invoke `Go to Definition` and `Alt+Click` stand for `Inspect Type at Point`.
       If you want to disable these bindings or change them bindings to something else,
       adjust the config at `Preferences > Package Settings > Mousemap - Default`.

    c. For Windows users, make sure the Line Endings setting in Sublime Text 2 is set to Unix.
       You may do this by going to View > Line Endings and selecting 'Unix'.

## How to use?

Open the Sublime command palette (typically bound to `Ctrl+Shift+P` on Windows/Linux and `Cmd+Shift+P` on Mac) and type `Ensime: Startup`.

If you don't have an Ensime project, the plugin will guide you through creating it.

If you already have a project, an ENSIME server process will be started in the background,
and the server will initialize a resident instance of the Scala compiler.
After the server is ready, a message will appear in the left-hand corner of the status bar.
It will read either `ENSIME` if the currently opened file belongs to the active Ensime project
or `ensime` if it doesn't. Keep an eye on this message - it's an indicator of things going well.

## Troubleshooting

If you find that some features of ensime are not working properly (i.e. Go To Definition or Error Highlighting), then check the Line Endings setting in Sublime Text 2.  On Windows, the line endings is set to 'Windows' by default.  Simply change this setting to 'Unix' by going to View > Line Endings and selecting 'Unix'.

## Contacts

In case if something goes wrong, let us know at dev@sublimescala.org or
submit an issue to the tracker https://github.com/sublimescala/sublime-ensime/issues/new.
Regards, the SublimeScala team.
