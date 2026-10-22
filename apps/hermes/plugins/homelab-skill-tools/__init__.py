"""Selection only; skill discovery, loading and handlers remain Hermes-native.

Uses the installed v0.22.3 toolset API. Revalidate on Hermes upgrades.
No tool overrides, new handlers, execution hooks, or dependency installation.
"""


def register(ctx):
    from toolsets import create_custom_toolset

    create_custom_toolset(
        "homelab-skills-read",
        "Native skill discovery and loading without authoring",
        tools=["skills_list", "skill_view"],
    )
