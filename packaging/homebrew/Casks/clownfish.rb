cask "clownfish" do
  version "0.5.0"
  sha256 "54eeed0236e8d0b909bff65661f682cccffbb186f4f6dbf3c5eb6c54bb03f2b9"

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
