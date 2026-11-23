# BlockNote notices — Notes editor milestone

## Kanban drag and drop

The Kanban UI imports the unmodified published `@dnd-kit/react` package, pinned to 0.5.3, with its dnd-kit dependencies. Upstream: https://github.com/clauderic/dnd-kit. Copyright (c) 2021, Claudéric Demers; MIT License, preserved at `public/licenses/dnd-kit/MIT.txt`. No PLANKA or Morchitask source/assets were copied.

Installed, unmodified official packages: `@blocknote/core`, `@blocknote/react`, `@blocknote/ariakit`, each **0.57.0**, each declaring **MPL-2.0** in its installed package metadata. The lockfile pins their exact distribution integrity. No `@blocknote/xl-*`, paid Pro package or AI/collaboration service is installed or enabled.

Upstream source and license: https://github.com/TypeCellOS/BlockNote and https://github.com/TypeCellOS/BlockNote/blob/main/LICENSE.txt. Corresponding core source revision from npm metadata: https://github.com/TypeCellOS/BlockNote/tree/37614ab348dcc7faa830a9a88437b37197a2162d/packages/core. React source revision from npm metadata: https://github.com/TypeCellOS/BlockNote/tree/d5e8c96e2ad5f6832da60bc3c9acd3f6c16c25c5/packages/react. The React and Ariakit distributions also contain their TSX `src/`; the core distribution contains compiled code/declarations and its original license/notices. Ariakit's registry metadata does not provide a gitHead. Exact pinned distributions: https://registry.npmjs.org/@blocknote/core/-/core-0.57.0.tgz, https://registry.npmjs.org/@blocknote/react/-/react-0.57.0.tgz, https://registry.npmjs.org/@blocknote/ariakit/-/ariakit-0.57.0.tgz.

The shipped MPL license is preserved at `public/licenses/blocknote/MPL-2.0.txt`; upstream third-party notices (MIT emoji data and Unicode License V3 data) are preserved unchanged at `public/licenses/blocknote/NOTICE.txt`. Ariakit declares MIT. Package source files were not copied into or modified inside Yggdress; this integration imports the published libraries.

The public versioned release/source archive is also available at https://github.com/TypeCellOS/BlockNote/releases/tag/v0.57.0 and https://github.com/TypeCellOS/BlockNote/archive/refs/tags/v0.57.0.tar.gz. Preserve corresponding source availability when distributing an executable build.

For distribution, retain these notices and make the corresponding covered BlockNote source available as required by MPL 2.0. Any future modifications to covered library files must retain their notices and be made available under MPL 2.0; separate application files do not acquire that file-level license merely by importing the library. Do not substitute an XL package without separate authorization. This records upstream terms rather than providing legal advice.

The pre-existing image tooling/Next.js image dependency tree includes libvips LGPL notices; these are unrelated to BlockNote. The dependency audit findings for existing Vitest/tinypool/sharp development tools are recorded in the milestone report; no unrelated major dependency upgrade is performed here.
