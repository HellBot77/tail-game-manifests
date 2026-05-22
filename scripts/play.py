from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from anyio import Path
from anyio import run
from play_launcher_sdk import AsyncLauncher
from play_launcher_sdk import ChinaLauncherId
from play_launcher_sdk import GameBiz
from play_launcher_sdk import GlobalLauncherId
from pydantic import HttpUrl
from tail_launcher_sdk.enums import DiffType
from tail_launcher_sdk.enums import DirType
from tail_launcher_sdk.enums import DownloadMode
from tail_launcher_sdk.enums import RegionCode
from tail_launcher_sdk.models import GameManifest
from tail_launcher_sdk.models.diff_audio_file import DiffAudioFile
from tail_launcher_sdk.models.diff_game_file import DiffGameFile
from tail_launcher_sdk.models.diff_urls import DiffUrls
from tail_launcher_sdk.models.full_audio_file import FullAudioFile
from tail_launcher_sdk.models.full_game_file import FullGameFile
from tail_launcher_sdk.models.game_paths import GamePaths
from tail_launcher_sdk.models.game_version import GameVersion
from tail_launcher_sdk.models.version_assets import VersionAssets
from tail_launcher_sdk.models.version_audio_files import VersionAudioFiles
from tail_launcher_sdk.models.version_game_files import VersionGameFiles
from tail_launcher_sdk.models.version_metadata import VersionMetadata

if TYPE_CHECKING:
    from collections.abc import Iterable

    from play_launcher_sdk.models.game_package import GamePackage
    from pydantic_extra_types.semantic_version import SemanticVersion

PLAY_ID_TO_TAIL_REGION = {
    GlobalLauncherId.EPIC_GOOGLE_HONKAI_IMPACT_3RD_ASIA: RegionCode.ASIA,
    GlobalLauncherId.EPIC_GOOGLE_HONKAI_IMPACT_3RD_GLOBAL: RegionCode.GLB,
    GlobalLauncherId.EPIC_GOOGLE_HONKAI_IMPACT_3RD_JAPAN: RegionCode.JP,
    GlobalLauncherId.EPIC_GOOGLE_HONKAI_IMPACT_3RD_KOREA: RegionCode.KR,
    GlobalLauncherId.EPIC_GOOGLE_HONKAI_IMPACT_3RD_SEA: RegionCode.OVERSEAS,
}


def find[T](models: list[T], biz: GameBiz) -> T | None:
    for model in models:
        # noinspection PyUnresolvedReferences
        if getattr(model, "game", model).biz == biz:
            return model

    return None


def index_version(manifest: GameManifest, version: SemanticVersion) -> int | None:
    for index, game_version in enumerate(manifest.game_versions):
        if game_version.metadata.version == version:
            return index

    return None


async def get_paths(launcher: AsyncLauncher, biz: GameBiz) -> GamePaths:
    configs = await launcher.get_game_configs()
    config = find(configs.launch_configs, biz)
    assert config is not None

    return GamePaths(
        audio_pkg_res_dir=PurePosixPath(config.audio_pkg_res_dir),
        exe_filename=PurePosixPath(config.exe_file_name),
        installation_dir=PurePosixPath(config.installation_dir),
        screenshot_dir=PurePosixPath(config.game_screenshot_dir),
        screenshot_dir_relative_to=(
            DirType.DATA if config.game_screenshot_dir.parts[0].endswith("_Data") else DirType.GAME
        ),
    )


async def get_assets(launcher: AsyncLauncher, biz: GameBiz) -> VersionAssets | None:
    all_basic_info = await launcher.get_all_game_basic_info()
    info = find(all_basic_info.game_info_list, biz)
    assert info is not None

    games = await launcher.get_games()
    status = find(games.games, biz)
    assert status is not None

    for background in info.backgrounds:
        assert status.display.icon.url != ""
        assert background.background.url != ""

        return VersionAssets(
            game_icon=status.display.icon.url,
            game_background=background.background.url,
            game_live_background=background.video.url,
        )

    return None


def play_package_to_tail_version(package: GamePackage) -> GameVersion:
    return GameVersion(
        metadata=VersionMetadata(
            versioned_name="",
            version=package.main.major.version,
            download_mode=DownloadMode.FILE,
            game_hash="",
            index_file="",
            res_list_url=package.main.major.res_list_url,
            diff_list_url=DiffUrls(game="", en_us="", zh_cn="", ja_jp="", ko_kr=""),
        ),
        assets=VersionAssets(
            game_icon=HttpUrl("https://example.com/icon.png"),
            game_background=HttpUrl("https://example.com/background.jpg"),
            game_live_background="",
        ),
        game=VersionGameFiles(
            full=[
                FullGameFile(
                    file_url=game_pkg.url,
                    compressed_size=game_pkg.size,
                    decompressed_size=game_pkg.decompressed_size,
                    file_hash=game_pkg.md5.hex(),
                    file_path="",
                    region_code="",
                )
                for game_pkg in package.main.major.game_pkgs
            ],
            diff=[
                DiffGameFile(
                    file_url=game_pkg.url,
                    compressed_size=game_pkg.size,
                    decompressed_size=game_pkg.decompressed_size,
                    file_hash=game_pkg.md5.hex(),
                    file_path="",
                    diff_type=DiffType.HDIFF,
                    original_version=patch.version,
                    delete_files=[],
                )
                for patch in package.main.patches
                for game_pkg in patch.game_pkgs
            ],
        ),
        audio=VersionAudioFiles(
            full=[
                FullAudioFile(
                    file_url=audio_pkg.url,
                    compressed_size=audio_pkg.size,
                    decompressed_size=audio_pkg.decompressed_size,
                    file_hash=audio_pkg.md5.hex(),
                    file_path="",
                    language=audio_pkg.language,
                    region_code="",
                )
                for audio_pkg in package.main.major.audio_pkgs
            ],
            diff=[
                DiffAudioFile(
                    file_url=audio_pkg.url,
                    compressed_size=audio_pkg.size,
                    decompressed_size=audio_pkg.decompressed_size,
                    file_hash=audio_pkg.md5.hex(),
                    file_path="",
                    diff_type=DiffType.HDIFF,
                    original_version=patch.version,
                    language=audio_pkg.language,
                )
                for patch in package.main.patches
                for audio_pkg in patch.audio_pkgs
            ],
        ),
    )


async def get_version(launcher: AsyncLauncher, biz: GameBiz) -> GameVersion:
    packages = await launcher.get_game_packages()
    package = find(packages.game_packages, biz)
    assert package is not None
    version = play_package_to_tail_version(package)

    assets = await get_assets(launcher, biz)
    if assets is not None:
        version = version.model_copy(update={"assets": assets})

    return version


def update_region_code(version: GameVersion, region_code: RegionCode) -> None:
    for index, file in enumerate(version.game.full):
        version.game.full[index] = file.model_copy(update={"region_code": region_code})

    for index, file in enumerate(version.audio.full):
        version.audio.full[index] = file.model_copy(update={"region_code": region_code})


async def get_version_bh3(launcher: AsyncLauncher, append_ids: Iterable[GlobalLauncherId]) -> GameVersion:
    assert isinstance(launcher.id, GlobalLauncherId)
    version = await get_version(launcher, GameBiz.HONKAI_IMPACT_3RD_GLOBAL)
    update_region_code(version, PLAY_ID_TO_TAIL_REGION[launcher.id])

    for append_id in append_ids:
        append_launcher = AsyncLauncher(append_id)
        append_version = await get_version(append_launcher, GameBiz.HONKAI_IMPACT_3RD_GLOBAL)
        update_region_code(append_version, PLAY_ID_TO_TAIL_REGION[append_id])

        version.game.full.extend(append_version.game.full)
        version.audio.full.extend(append_version.audio.full)

    return version


async def append_manifest(launcher: AsyncLauncher, biz: GameBiz) -> None:
    path = await Path.cwd() / "generated" / f"{biz}.json"
    print(f"[#] {biz}: {path}")

    read = await path.read_text()
    manifest = GameManifest.model_validate_json(read)

    if biz == GameBiz.HONKAI_IMPACT_3RD_GLOBAL:
        assert isinstance(launcher.id, GlobalLauncherId)
        append_ids = list(PLAY_ID_TO_TAIL_REGION)
        append_ids.remove(launcher.id)

        version = await get_version_bh3(launcher, append_ids)
    else:
        version = await get_version(launcher, biz)

    parts = manifest.display_name.rsplit(maxsplit=1)
    parts.insert(1, str(version.metadata.version))
    version = version.model_copy(
        update={"metadata": version.metadata.model_copy(update={"versioned_name": " ".join(parts)})}
    )

    index = index_version(manifest, version.metadata.version)
    if index is None:
        print(f"[+] {biz}: {version.metadata.version}")
        manifest.game_versions.insert(0, version)
    else:
        print(f"[~] {biz}: {version.metadata.version}")
        manifest.game_versions[index] = version

    paths = await get_paths(launcher, biz)
    manifest = manifest.model_copy(
        update={"latest_version": version.metadata.version, "paths": paths, "assets": version.assets}
    )
    write = manifest.model_dump_json(indent=2)

    if read == write:
        print(f"[=] {biz}: {path}")
    else:
        print(f"[!] {biz}: {path}")
        await path.write_text(write)


async def main() -> None:
    play = {
        GlobalLauncherId.EPIC_GOOGLE_HONKAI_IMPACT_3RD_GLOBAL: (GameBiz.HONKAI_IMPACT_3RD_GLOBAL,),
        GlobalLauncherId.OFFICIAL: (
            GameBiz.GENSHIN_IMPACT_GLOBAL,
            GameBiz.HONKAI_STAR_RAIL_GLOBAL,
            GameBiz.ZENLESS_ZONE_ZERO_GLOBAL,
        ),
        ChinaLauncherId.OFFICIAL: (
            GameBiz.GENSHIN_IMPACT_CHINA,
            GameBiz.HONKAI_IMPACT_3RD_CHINA,
            GameBiz.HONKAI_STAR_RAIL_CHINA,
            GameBiz.ZENLESS_ZONE_ZERO_CHINA,
        ),
    }

    for id_, bizs in play.items():
        launcher = AsyncLauncher(id_)
        for biz in bizs:
            await append_manifest(launcher, biz)


if __name__ == "__main__":
    run(main)
