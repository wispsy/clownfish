cask "clownfish" do
  version "0.6.3"
  sha256 "326406ae218c3e2009877bfb137d51daf74f476e9d73e92a0baef5641987f890"

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
