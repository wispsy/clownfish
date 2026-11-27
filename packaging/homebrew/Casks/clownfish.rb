cask "clownfish" do
  version "0.7.0"
  sha256 "663ad5913fec5f14298e6437174229434fb63057873e9a1d64aa8cc6e62ba857"

  url "https://github.com/wispsy/clownfish/releases/download/v#{version}/Clownfish-v#{version}-macos.zip"
  name "Clownfish"
  desc "Lightweight, zero-dependency modern terminal emulator"
  homepage "https://github.com/wispsy/clownfish"

  app "Clownfish.app"
  binary "#{appdir}/Clownfish.app/Contents/MacOS/Clownfish", target: "clownfish"

  zap trash: [
    "~/.config/clownfish",
    "~/Library/Saved Application State/tech.wispsy.clownfish.savedState",
  ]
end
