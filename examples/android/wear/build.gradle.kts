plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.crashguard.wear"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.crashguard.app"   // same id as phone app (required for Wear data layer)
        minSdk = 30
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    sourceSets["main"].assets.srcDir("../shared-assets")
}

dependencies {
    implementation(project(":core"))
    implementation("com.google.android.gms:play-services-wearable:18.2.0")
}
