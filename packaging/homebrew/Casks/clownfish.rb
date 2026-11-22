cask "clownfish" do
  version "0.6.3"
  sha256 "8511311e72841cbbeb20f38a7924f8f3256f3ad0c3e35ea1643923307bcb6eba"

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
