# /// script
# dependencies = [
#   "anyio",
#   "pydantic-extra-types[semver]",
#
#   "play-launcher-sdk @ git+https://github.com/HellLord77/play-launcher-sdk.git@v0.2.2",
#   "tail-launcher-sdk @ git+https://github.com/HellLord77/tail-launcher-sdk.git@v0.2.3",
# ]
# ///

from anyio import Path, run
from play_launcher_sdk import AsyncLauncher, ChinaId, GameBiz, GlobalId
from play_launcher_sdk.id import Id
from play_launcher_sdk.models.game_package import GamePackage
from pydantic_extra_types.semantic_version import SemanticVersion
from tail_launcher_sdk.enums import DiffType, DownloadMode
from tail_launcher_sdk.models import GameManifest
from tail_launcher_sdk.models.diff_audio_file import DiffAudioFile
from tail_launcher_sdk.models.diff_game_file import DiffGameFile
from tail_launcher_sdk.models.diff_urls import DiffUrls
from tail_launcher_sdk.models.full_audio_file import FullAudioFile
from tail_launcher_sdk.models.full_game_file import FullGameFile
from tail_launcher_sdk.models.game_version import GameVersion
from tail_launcher_sdk.models.version_assets import VersionAssets
from tail_launcher_sdk.models.version_audio_files import VersionAudioFiles
from tail_launcher_sdk.models.version_game_files import VersionGameFiles
from tail_launcher_sdk.models.version_metadata import VersionMetadata


def find_package(packages: list[GamePackage], biz: GameBiz) -> GamePackage | None:
    for package in packages:
        if package.game.biz == biz:
            return package
    return None


def index_version(manifest: GameManifest, version: SemanticVersion) -> int | None:
    for index, game_version in enumerate(manifest.game_versions):
        if game_version.metadata.version == version:
            return index
    return None


def play_package_to_tail_version(
    package: GamePackage, assets: VersionAssets
) -> GameVersion:
    version = GameVersion(
        metadata=VersionMetadata(
            versioned_name="",
            version=package.main.major.version,
            download_mode=DownloadMode.FILE,
            game_hash="",
            index_file="",
            res_list_url="",
            diff_list_url=DiffUrls(game="", en_us="", zh_cn="", ja_jp="", ko_kr=""),
        ),
        assets=assets,
        game=VersionGameFiles(full=[], diff=[]),
        audio=VersionAudioFiles(full=[], diff=[]),
    )

    for game_pkg in package.main.major.game_pkgs:
        file = FullGameFile(
            file_url=game_pkg.url,
            compressed_size=game_pkg.size,
            decompressed_size=game_pkg.decompressed_size,
            file_hash=game_pkg.md5.hex(),
            file_path="",
            region_code="",
        )
        version.game.full.append(file)

    for audio_pkg in package.main.major.audio_pkgs:
        file = FullAudioFile(
            file_url=audio_pkg.url,
            compressed_size=audio_pkg.size,
            decompressed_size=audio_pkg.decompressed_size,
            file_hash=audio_pkg.md5.hex(),
            file_path="",
            language=audio_pkg.language,
            region_code="",
        )
        version.audio.full.append(file)

    for patch in package.main.patches:
        for game_pkg in patch.game_pkgs:
            file = DiffGameFile(
                file_url=game_pkg.url,
                compressed_size=game_pkg.size,
                decompressed_size=game_pkg.decompressed_size,
                file_hash=game_pkg.md5.hex(),
                file_path="",
                diff_type=DiffType.HDIFF,
                original_version=patch.version,
                delete_files=[],
            )
            version.game.diff.append(file)

        for audio_pkg in patch.audio_pkgs:
            file = DiffAudioFile(
                file_url=audio_pkg.url,
                compressed_size=audio_pkg.size,
                decompressed_size=audio_pkg.decompressed_size,
                file_hash=audio_pkg.md5.hex(),
                file_path="",
                diff_type=DiffType.HDIFF,
                original_version=patch.version,
                language=audio_pkg.language,
            )
            version.audio.diff.append(file)

    return version


async def append(id: Id, biz: GameBiz):
    path = Path(__file__).parent / "generated" / f"{biz}.json"
    print(f"[#] {biz}: {path}")

    launcher = AsyncLauncher(id)
    packages = await launcher.get_game_packages()

    read = await path.read_text()
    manifest = GameManifest.model_validate_json(read)

    package = find_package(packages.game_packages, biz)
    assert package is not None
    version = play_package_to_tail_version(package, manifest.assets)

    index = index_version(manifest, package.main.major.version)
    if index is None:
        print(f"[+] {biz}: {package.main.major.version}")
        manifest.game_versions.insert(0, version)
    else:
        print(f"[~] {biz}: {package.main.major.version}")
        manifest.game_versions[index] = version

    manifest = manifest.model_copy(
        update={"latest_version": package.main.major.version}
    )
    write = manifest.model_dump_json(indent=2)

    print(f"[{'=' if read == write else '*'}] {biz}: {path}")
    await path.write_text(write)


async def main():
    play = {
        GlobalId.OFFICIAL: (
            GameBiz.HONKAI_STAR_RAIL_GLOBAL,
            GameBiz.ZENLESS_ZONE_ZERO_GLOBAL,
        ),
        ChinaId.OFFICIAL: (
            GameBiz.HONKAI_STAR_RAIL_CHINA,
            GameBiz.ZENLESS_ZONE_ZERO_CHINA,
        ),
    }

    for id, bizs in play.items():
        for biz in bizs:
            await append(id, biz)


if __name__ == "__main__":
    run(main)
