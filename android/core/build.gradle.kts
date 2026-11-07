plugins {
    id("org.jetbrains.kotlin.jvm")
}

kotlin { jvmToolchain(17) }

dependencies {
    // Android ships org.json at runtime; JVM unit tests need the real artifact.
    compileOnly("org.json:json:20231013")
    testImplementation("org.json:json:20231013")
    testImplementation("junit:junit:4.13.2")
}

tasks.test {
    useJUnit()
    systemProperty("model.path", rootProject.file("shared-assets/crash_model.json").absolutePath)
    systemProperty("parity.path", rootProject.file("../ml/model/parity.json").absolutePath)
}
