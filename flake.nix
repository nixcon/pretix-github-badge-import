{
  inputs.flake-parts.url = "github:hercules-ci/flake-parts";
  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
  inputs.devenv.url = "github:cachix/devenv";

  outputs = inputs: inputs.flake-parts.lib.mkFlake { inherit inputs; } {
    imports = [ inputs.devenv.flakeModule ];
    systems = [ "x86_64-linux" "aarch64-linux" ];
    perSystem = { pkgs, lib, ... }: let
      pythonEnv = develop: pkgs.python3.withPackages (p: [ p.requests p.types-requests p.diskcache ] ++ (lib.optional develop p.mypy));
    in {
      packages.default = pkgs.stdenv.mkDerivation {
        name = "badge-import";
        src = ./import.py;

        nativeBuildInputs = [ (pythonEnv false) ];

        phases = [ "buildPhase" "installPhase" ]; 

        buildPhase = ''
          ${pythonEnv true}/bin/mypy $src
        '';

        installPhase = ''
          mkdir -p $out/bin/import
          cp $src $out/bin/import
          patchShebangs $out/bin/import
        '';
      };
      devenv.shells.default = {
        packages = [ (pythonEnv true) pkgs.python3Packages.pytest pkgs.python3Packages.python-lsp-server ];
      };
    };
  };
}
